// SPEX RTL timing spike (owner task, 2026-10-22): the engine's critical loop, to measure the clock it closes at.
// NOT the SPEX RTL: no actions, violations, coverage, events, FIFOs or host port; tables load through a scan chain.
// What it keeps is everything between the held edge-macro output and the next macro address (SEMANTICS v1):
//   DOUT (4 edge words, R4.2, R11.1) -> pattern / window / constant table reads (4 ports each)
//   -> pin guard LEVEL/EDGE over pending changes (R2.4, R5.2) -> trigger age (R5.4) -> v = max(x_c - a, 0) (R2.5)
//   -> clock guard GE / WIN / POLICY against the latched t_e (R2.5, R8.1: earliest policy) -> data guard (R2.6)
//   -> lowest enabled slot (R3.2) -> target -> macro address and read enable (R4.2), clock resets x := 1 + a (R1.6).
// Written in a conservative SystemVerilog subset (no return, no casts) so every Yosys front end reads it.
// SPDX-License-Identifier: Apache-2.0
`default_nettype none

module spex_loop (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [7:0]   pins,       // P_n: the synchronised pin bus (R4.1)
    input  logic [127:0] edge_q,     // slot i = edge_q[32*i +: 32], from 2 x RM_IHPSG13_1P_64x64 (held DOUT)
    input  logic         cfg_shift,  // scan the tables (host port stand-in)
    input  logic         cfg_in,
    output logic         cfg_out,
    input  logic         start,      // R12.4
    output logic [5:0]   mem_addr,   // next location: the macros read it at the firing cycle's clock edge
    output logic         mem_ren,
    output logic [5:0]   loc,
    output logic         fired,
    output logic [1:0]   fslot,
    output logic [15:0]  ts          // v of the fired edge (R5.6), keeps the age/clock path observable
);
    localparam XW = 16;
    localparam [1:0] ST_STOPPED = 2'd0, ST_ENTRY = 2'd1, ST_EVAL = 2'd2;

    // ---------------------------------------------------------------- tables, one scan chain
    // windows {clk 2, hi 16, lo 16} x 16 | patterns {mode 1, value 8, mask 8} x 8 | constants 16 x 8 | tok head 8 | txf 1
    localparam WWIN = 34, WPAT = 17, WK = 16;
    localparam OPAT = 16 * WWIN, OK = OPAT + 8 * WPAT, OTOK = OK + 8 * WK, OTXF = OTOK + 8, CFGW = OTXF + 1;
    logic [CFGW-1:0] cfg;
    always_ff @(posedge clk) if (cfg_shift) cfg <= {cfg[CFGW-2:0], cfg_in};
    assign cfg_out = cfg[CFGW-1];

    wire [WWIN-1:0] win  [0:15];
    wire [WPAT-1:0] pat  [0:7];
    wire [WK-1:0]   kon  [0:7];
    genvar j;
    generate
        for (j = 0; j < 16; j = j + 1) begin : g_win
            assign win[j] = cfg[j*WWIN +: WWIN];
        end
        for (j = 0; j < 8; j = j + 1) begin : g_pk
            assign pat[j] = (j == 0) ? {WPAT{1'b0}} : cfg[OPAT + j*WPAT +: WPAT];     // pattern 0 = none
            assign kon[j] = cfg[OK + j*WK +: WK];
        end
    endgenerate
    wire [7:0] tok_head = cfg[OTOK +: 8];
    wire       txf_ne   = cfg[OTXF];

    // ---------------------------------------------------------------- engine state
    logic [1:0]    st;
    logic          first;
    logic [7:0]    pin_prev, pend1, pend2;
    logic [XW-1:0] x0, x1, x2;
    logic [XW-1:0] t_e [0:3];
    logic [7:0]    sr;
    logic [5:0]    bitcnt;

    wire [7:0] chg  = pins ^ pin_prev;
    wire [7:0] a1   = first ? pend1 : 8'h00;
    wire [7:0] a2   = first ? pend2 : 8'h00;
    wire [7:0] pend = chg | a1 | a2;

    // ---------------------------------------------------------------- 4 guard slots in parallel
    wire [3:0]    en;
    wire [1:0]    age  [0:3];
    wire [XW-1:0] v    [0:3];
    wire [7:0]    tm   [0:3];
    wire [XW-1:0] lo_s [0:3];
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : g_slot
            wire [31:0]     e      = edge_q[32*i +: 32];
            wire [WPAT-1:0] p      = pat[e[24:22]];
            wire [7:0]      m      = p[7:0];
            wire            lvl    = ((pins & m) == (p[15:8] & m));
            wire [7:0]      trig   = pend & m;
            wire            pin_ok = lvl && (!p[16] || (|trig));                    // p[16] = EDGE mode (R2.4)
            assign tm[i]  = m;
            // R5.4: the smallest age among pending trigger pins
            assign age[i] = |(trig & chg) ? 2'd0 : |(trig & a1) ? 2'd1 : |(trig & a2) ? 2'd2 : 2'd0;
            wire [WWIN-1:0] w   = win[{e[2], e[21:19]}];
            wire [XW-1:0]   lo  = w[XW-1:0];
            wire [XW-1:0]   hi  = w[2*XW-1:XW];
            wire [XW-1:0]   xc  = (w[WWIN-1:WWIN-2] == 2'd0) ? x0 : (w[WWIN-1:WWIN-2] == 2'd1) ? x1 : x2;
            wire [XW-1:0]   a16 = {14'd0, age[i]};
            assign v[i]    = (xc > a16) ? xc - a16 : {XW{1'b0}};                   // R2.5 trigger instant
            assign lo_s[i] = lo;
            wire [WK-1:0]   kk  = kon[e[13:11]];
            reg ck_ok, dat_ok;
            always @(*) begin
                case (e[18:17])
                    2'd0:    ck_ok = 1'b1;                                           // NONE
                    2'd1:    ck_ok = v[i] >= lo;                                     // GE
                    2'd2:    ck_ok = (v[i] >= lo) && (v[i] <= hi);                   // WIN
                    default: ck_ok = (v[i] >= t_e[i]) && (v[i] <= hi);               // POLICY
                endcase
                case (e[16:14])
                    3'd0:    dat_ok = 1'b1;
                    3'd1:    dat_ok = {2'b00, bitcnt} == kk[7:0];
                    3'd2:    dat_ok = {2'b00, bitcnt} <  kk[7:0];
                    3'd3:    dat_ok = (sr & kk[15:8]) == (kk[7:0] & kk[15:8]);
                    3'd4:    dat_ok = 1'b0;                                          // events: not in the spike
                    3'd5:    dat_ok = txf_ne;
                    3'd6:    dat_ok = tok_head == kk[7:0];
                    default: dat_ok = (sr & kk[15:8]) != (kk[7:0] & kk[15:8]);
                endcase
            end
            assign en[i] = (st == ST_EVAL) && e[1] && pin_ok && ck_ok && dat_ok;
        end
    endgenerate

    // ---------------------------------------------------------------- priority and next location (R3.2)
    wire        any = |en;
    wire [1:0]  sel = en[0] ? 2'd0 : en[1] ? 2'd1 : en[2] ? 2'd2 : 2'd3;
    wire [31:0] fe  = edge_q[32*sel +: 32];
    assign mem_addr = start ? 6'd0 : fe[30:25];
    assign mem_ren  = start | any;
    wire [XW-1:0] x_reset = 16'd1 + {14'd0, age[sel]};                             // R1.6

    function [XW-1:0] inc_sat(input [XW-1:0] xv);
        inc_sat = (xv == 16'hFFFF) ? xv : xv + 16'd1;
    endfunction

    // ---------------------------------------------------------------- state update (R3.6, R3.7)
    integer s;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= ST_STOPPED; first <= 1'b0; loc <= 6'd0; pend1 <= 8'd0; pend2 <= 8'd0; pin_prev <= 8'd0;
            x0 <= 16'd0; x1 <= 16'd0; x2 <= 16'd0;
            for (s = 0; s < 4; s = s + 1) t_e[s] <= 16'd0;
            sr <= 8'd0; bitcnt <= 6'd0; fired <= 1'b0; fslot <= 2'd0; ts <= 16'd0;
        end else begin
            pin_prev <= pins;
            fired <= 1'b0;
            x0 <= inc_sat(x0); x1 <= inc_sat(x1); x2 <= inc_sat(x2);
            if (start) begin
                st <= ST_ENTRY; loc <= 6'd0; first <= 1'b0; pend1 <= 8'd0; pend2 <= 8'd0;
                x0 <= 16'd1; x1 <= 16'd1; x2 <= 16'd1;
            end else if (st == ST_ENTRY) begin
                st <= ST_EVAL; first <= 1'b1; pend1 <= chg;
                for (s = 0; s < 4; s = s + 1) t_e[s] <= lo_s[s];                     // earliest policy (R8.1)
            end else if (st == ST_EVAL) begin
                first <= 1'b0;
                if (any) begin
                    st <= ST_ENTRY; loc <= fe[30:25]; fired <= 1'b1; fslot <= sel; ts <= v[sel];
                    pend2 <= pend & ~tm[sel]; pend1 <= 8'd0;                          // R5.5 carry-over
                    if (fe[4]) x0 <= x_reset;
                    if (fe[5]) x1 <= x_reset;
                    if (fe[6]) x2 <= x_reset;
                    // one datapath op so the data guards see changing state: SHIN of pin 0, or CLR
                    if (fe[7]) begin
                        sr <= {sr[6:0], pins[0]};
                        bitcnt <= (bitcnt == 6'd63) ? bitcnt : bitcnt + 6'd1;
                    end else if (fe[8]) begin
                        bitcnt <= 6'd0;
                    end
                end else begin
                    pend1 <= 8'd0; pend2 <= 8'd0;
                end
            end
        end
    end
endmodule
