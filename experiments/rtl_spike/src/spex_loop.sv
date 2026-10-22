// SPEX RTL timing spike v2 (owner decisions 2026-10-22): one engine's critical loop, split as R3.5/R4.2 allow.
// NOT the SPEX RTL: no events, FIFOs, coverage, trace, host port or LFSR policies; tables load through a scan chain.
//
//   ENTRY cycle (path A): held macro output (4 edge words, location word) -> pattern / window / constant table reads
//                         -> per-slot registers {target, pattern, window, t_e, data guard + constant, action, resets}
//                         and the location's watch mask and invariant {clock, hi}.
//   EVAL cycle  (path B): slot registers, pins, pending masks, clocks with their history -> pin / clock / data guards
//                         -> lowest enabled slot (R3.2), or a violation (R6.1, R6.2) -> next location -> macro
//                         address. No table read and no macro output on this path.
//   action path:          fired slot -> action table -> pin writes and datapath op -> registers (R2.9, R2.10).
// v = max(x_c - a, 0) (R2.5) is a 3:1 select of x, x_d1, x_d2 by the age (spex/refsim/clock_history.py).
// Written in a conservative SystemVerilog subset (no return, no casts) so every Yosys front end reads it.
// SPDX-License-Identifier: Apache-2.0
`default_nettype none

module spex_loop (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [7:0]   pins,       // P_n: the synchronised pin bus (R4.1)
    input  logic [127:0] edge_q,     // slot i = edge_q[32*i +: 32], from 2 x RM_IHPSG13_1P_64x64 (held DOUT, R4.2)
    input  logic [15:0]  lw_q,       // location word from RM_IHPSG13_1P_64x16 (R11.6), same address
    input  logic         cfg_shift,  // scan the tables (host port stand-in)
    input  logic         cfg_in,
    output logic         cfg_out,
    input  logic         start,      // R12.4
    output logic [5:0]   mem_addr,   // next location: the macros read it at the firing cycle's clock edge
    output logic         mem_ren,
    output logic [5:0]   loc,
    output logic         fired,
    output logic         viol,
    output logic [7:0]   pout,
    output logic [7:0]   poe,
    output logic [15:0]  ts
);
    localparam XW = 16;
    localparam [1:0] ST_STOPPED = 2'd0, ST_ENTRY = 2'd1, ST_EVAL = 2'd2, ST_HALTED = 2'd3;

    // ---------------------------------------------------------------- tables, one scan chain (R11.2-R11.5)
    // windows {clk 2, hi 16, lo 16} x 16 | patterns {mode, value 8, mask 8} x 8 | constants 16 x 8 | actions 32 x 16
    // | TX byte stand-in 8 | drive_en 1
    localparam WWIN = 34, WPAT = 17, WK = 16, WACT = 32;
    localparam OPAT = 16 * WWIN, OK = OPAT + 8 * WPAT, OACT = OK + 8 * WK, OTX = OACT + 16 * WACT, ODRV = OTX + 8;
    localparam CFGW = ODRV + 1;
    logic [CFGW-1:0] cfg;
    always_ff @(posedge clk) if (cfg_shift) cfg <= {cfg[CFGW-2:0], cfg_in};
    assign cfg_out = cfg[CFGW-1];

    wire [WWIN-1:0] win [0:15];
    wire [WPAT-1:0] pat [0:7];
    wire [WK-1:0]   kon [0:7];
    wire [WACT-1:0] act [0:15];
    genvar j;
    generate
        for (j = 0; j < 16; j = j + 1) begin : g_win
            assign win[j] = cfg[j*WWIN +: WWIN];
            assign act[j] = cfg[OACT + j*WACT +: WACT];
        end
        for (j = 0; j < 8; j = j + 1) begin : g_pk
            assign pat[j] = (j == 0) ? {WPAT{1'b0}} : cfg[OPAT + j*WPAT +: WPAT];     // pattern 0 = none
            assign kon[j] = cfg[OK + j*WK +: WK];
        end
    endgenerate
    wire [7:0] tx_byte  = cfg[OTX +: 8];
    wire       drive_en = cfg[ODRV];

    // ---------------------------------------------------------------- engine state
    logic [1:0]    st;
    logic          first;
    logic [7:0]    pin_prev, pend1, pend2;
    logic [7:0]    sr;
    logic [5:0]    bitcnt;
    // clocks and their history: d1 = max(x - 1, 0), d2 = max(x - 2, 0) in every cycle
    logic [XW-1:0] x  [0:2];
    logic [XW-1:0] d1 [0:2];
    logic [XW-1:0] d2 [0:2];

    // per-slot registers, written in the entry cycle
    logic          s_valid [0:3];
    logic [5:0]    s_tgt   [0:3];
    logic [7:0]    s_mask  [0:3];
    logic [7:0]    s_val   [0:3];
    logic          s_mode  [0:3];
    logic [1:0]    s_ck    [0:3];
    logic [1:0]    s_clk   [0:3];
    logic [XW-1:0] s_lo    [0:3];
    logic [XW-1:0] s_hi    [0:3];
    logic [XW-1:0] s_te    [0:3];
    logic [2:0]    s_dk    [0:3];
    logic [WK-1:0] s_k     [0:3];
    logic [3:0]    s_act   [0:3];
    logic [2:0]    s_rst   [0:3];
    // location registers, written in the entry cycle (R2.7, R11.6)
    logic [7:0]    l_watch;
    logic          l_inv_en;
    logic [1:0]    l_inv_clk;
    logic [XW-1:0] l_inv_hi;

    wire [7:0] chg  = pins ^ pin_prev;
    wire [7:0] a1   = first ? pend1 : 8'h00;
    wire [7:0] a2   = first ? pend2 : 8'h00;
    wire [7:0] pend = chg | a1 | a2;

    // ---------------------------------------------------------------- path A: entry-cycle decode and table reads
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : g_entry
            wire [31:0]     e = edge_q[32*i +: 32];
            wire [WPAT-1:0] p = pat[e[24:22]];
            wire [WWIN-1:0] w = win[{e[2], e[21:19]}];
            always_ff @(posedge clk) begin
                if (st == ST_ENTRY) begin
                    s_valid[i] <= e[1];
                    s_tgt[i]   <= e[30:25];
                    s_mask[i]  <= p[7:0];
                    s_val[i]   <= p[15:8];
                    s_mode[i]  <= p[16];
                    s_ck[i]    <= e[18:17];
                    s_clk[i]   <= w[WWIN-1:WWIN-2];
                    s_lo[i]    <= w[XW-1:0];
                    s_hi[i]    <= w[2*XW-1:XW];
                    s_te[i]    <= w[XW-1:0];                       // POLICY fire time, earliest policy (R8.1)
                    s_dk[i]    <= e[16:14];
                    s_k[i]     <= kon[e[13:11]];
                    s_act[i]   <= e[10:7];
                    s_rst[i]   <= e[6:4];
                end
            end
        end
    endgenerate
    wire [WWIN-1:0] inv_w = win[lw_q[11:8]];
    always_ff @(posedge clk) begin
        if (st == ST_ENTRY) begin
            l_watch   <= lw_q[7:0];
            l_inv_en  <= lw_q[12];
            l_inv_clk <= inv_w[WWIN-1:WWIN-2];
            l_inv_hi  <= inv_w[2*XW-1:XW];
        end
    end

    // ---------------------------------------------------------------- path B: guards from registers only
    wire [3:0]    en;
    wire [1:0]    age [0:3];
    wire [XW-1:0] v   [0:3];
    generate
        for (i = 0; i < 4; i = i + 1) begin : g_slot
            wire [7:0] m      = s_mask[i];
            wire       lvl    = ((pins & m) == (s_val[i] & m));
            wire [7:0] trig   = pend & m;
            wire       pin_ok = lvl && (!s_mode[i] || (|trig));                  // R2.4
            assign age[i] = |(trig & chg) ? 2'd0 : |(trig & a1) ? 2'd1 : |(trig & a2) ? 2'd2 : 2'd0;   // R5.4
            wire [1:0] c  = (s_clk[i] == 2'd3) ? 2'd2 : s_clk[i];
            assign v[i] = (age[i] == 2'd0) ? x[c] : (age[i] == 2'd1) ? d1[c] : d2[c];                  // R2.5
            reg ck_ok, dat_ok;
            always @(*) begin
                case (s_ck[i])
                    2'd0:    ck_ok = 1'b1;                                           // NONE
                    2'd1:    ck_ok = v[i] >= s_lo[i];                                // GE
                    2'd2:    ck_ok = (v[i] >= s_lo[i]) && (v[i] <= s_hi[i]);         // WIN
                    default: ck_ok = (v[i] >= s_te[i]) && (v[i] <= s_hi[i]);         // POLICY
                endcase
                case (s_dk[i])                                                       // R2.6, on S_n
                    3'd0:    dat_ok = 1'b1;
                    3'd1:    dat_ok = {2'b00, bitcnt} == s_k[i][7:0];
                    3'd2:    dat_ok = {2'b00, bitcnt} <  s_k[i][7:0];
                    3'd3:    dat_ok = (sr & s_k[i][15:8]) == (s_k[i][7:0] & s_k[i][15:8]);
                    3'd4:    dat_ok = 1'b0;                                          // events: not in the spike
                    3'd5:    dat_ok = 1'b1;                                          // TXF_NE: stand-in always ready
                    3'd6:    dat_ok = 1'b0;                                          // TOKEN: not in the spike
                    default: dat_ok = (sr & s_k[i][15:8]) != (s_k[i][7:0] & s_k[i][15:8]);
                endcase
            end
            assign en[i] = (st == ST_EVAL) && s_valid[i] && pin_ok && ck_ok && dat_ok;
        end
    endgenerate

    wire       any  = |en;
    wire [1:0] sel  = en[0] ? 2'd0 : en[1] ? 2'd1 : en[2] ? 2'd2 : 2'd3;
    wire [1:0] ic   = (l_inv_clk == 2'd3) ? 2'd2 : l_inv_clk;
    wire       unexp = |(pend & l_watch);                                         // R6.1
    wire       tmo   = l_inv_en && (x[ic] > l_inv_hi);                            // R6.2, current clock value
    wire       violate = (st == ST_EVAL) && !any && (unexp || tmo);
    assign mem_addr = (start || violate) ? 6'd0 : s_tgt[sel];                     // resync location 0 (R6.5)
    assign mem_ren  = start | any | violate;

    // ---------------------------------------------------------------- action path (R2.9, R2.10)
    wire [WACT-1:0] fa = act[s_act[sel]];
    wire [7:0] wm = fa[7:0];
    wire       od = fa[16];
    wire [2:0] dpin = fa[19:17];
    wire [3:0] op = fa[23:20];
    wire       outbit = sr[7];                                                    // msb_first
    wire [7:0] wv = (op == 4'd5) ? ((fa[15:8] & ~(8'h01 << dpin)) | ({7'd0, outbit} << dpin)) : fa[15:8];

    // ---------------------------------------------------------------- state update (R3.6, R3.7, R6.5)
    wire [1:0] ra = (start || violate) ? 2'd0 : age[sel];                       // start and resync: x := 1
    integer c;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= ST_STOPPED; first <= 1'b0; loc <= 6'd0; pend1 <= 8'd0; pend2 <= 8'd0; pin_prev <= 8'd0;
            sr <= 8'd0; bitcnt <= 6'd0; fired <= 1'b0; viol <= 1'b0; pout <= 8'd0; poe <= 8'd0; ts <= 16'd0;
            for (c = 0; c < 3; c = c + 1) begin x[c] <= 16'd0; d1[c] <= 16'd0; d2[c] <= 16'd0; end
        end else begin
            pin_prev <= pins;
            fired <= 1'b0;
            viol  <= 1'b0;
            for (c = 0; c < 3; c = c + 1) begin
                if (start || violate || (any && s_rst[sel][c])) begin               // x := 1 + a (R1.6)
                    x[c]  <= 16'd1 + {14'd0, ra};
                    d1[c] <= {14'd0, ra};
                    d2[c] <= (ra == 2'd0) ? 16'd0 : {14'd0, ra} - 16'd1;
                end else if (x[c] == 16'hFFFF) begin                               // saturated (R1.4)
                    d1[c] <= 16'hFFFE;
                    d2[c] <= 16'hFFFD;
                end else begin
                    x[c]  <= x[c] + 16'd1;
                    d1[c] <= x[c];
                    d2[c] <= d1[c];
                end
            end
            if (start) begin
                st <= ST_ENTRY; loc <= 6'd0; first <= 1'b0; pend1 <= 8'd0; pend2 <= 8'd0;
            end else if (st == ST_ENTRY) begin
                st <= lw_q[13] ? ST_HALTED : ST_EVAL;                              // R3.4
                first <= 1'b1; pend1 <= chg;
            end else if (st == ST_EVAL) begin
                first <= 1'b0;
                if (any) begin
                    st <= ST_ENTRY; loc <= s_tgt[sel]; fired <= 1'b1; ts <= v[sel];
                    pend2 <= pend & ~s_mask[sel]; pend1 <= 8'd0;                     // R5.5
                    if (drive_en) begin
                        if (od) poe  <= (poe & ~wm) | (~wv & wm);
                        else begin pout <= (pout & ~wm) | (wv & wm); poe <= poe | wm; end
                        if (od) pout <= pout & ~wm;
                    end
                    case (op)
                        4'd1: begin sr <= tx_byte; bitcnt <= 6'd0; end                // LOAD (TX byte stand-in)
                        4'd4, 4'd5: begin                                             // SHIN / SHOUT
                            sr <= {sr[6:0], (op == 4'd4) ? pins[dpin] : 1'b1};
                            bitcnt <= (bitcnt == 6'd63) ? bitcnt : bitcnt + 6'd1;
                        end
                        4'd8: bitcnt <= 6'd0;                                         // CLR
                        4'd10: bitcnt <= (bitcnt == 6'd63) ? bitcnt : bitcnt + 6'd1;  // INC
                        default: ;
                    endcase
                end else if (violate) begin
                    st <= ST_ENTRY; loc <= 6'd0; viol <= 1'b1; pend1 <= 8'd0; pend2 <= 8'd0;
                end else begin
                    pend1 <= 8'd0; pend2 <= 8'd0;
                end
            end
        end
    end
endmodule
