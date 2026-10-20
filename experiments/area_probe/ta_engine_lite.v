// Area probe v4: table formats of SEMANTICS v1 (S28, S33, S42). Not a design.
// Differences from v2: 16 windows x 62 bits {clk,nom,hi,lo}; 7 patterns x 17; 8 constants x 16;
// 16 actions x 32; 64 location words x 14 in FLOPS (R11.8: they do not fit the edge macros);
// 8-bit SR (S33); per-slot POLICY fire times; 32-bit LFSR (S26); events pending (R10.2).
module ta_engine_lite #(parameter CW = 20)(
  input clk, rst_n,
  input  [7:0] pins, input [7:0] ev_in, input [7:0] tok_head, input tok_valid,
  input  [127:0] edge_words, input [13:0] loc_word_in,  // location word from a 64x16 macro
  output reg [5:0] loc,
  output reg [7:0] pout, poe, ev_out,
  output reg viol, cov_stb, output reg [31:0] cov_word, output reg tok_pop,
  input cfg_we, input [9:0] cfg_addr, input [31:0] cfg_wdata,
  input [2:0] policy, input [CW-1:0] sweep_k, input drive_en,
  input tx_we, input [7:0] tx_byte, input rx_re, output [7:0] rx_byte
);
  reg [CW-1:0] wlo [0:7], whi [0:7]; reg [1:0] wck [0:7];
  reg [16:0] pat [1:7]; reg [15:0] kc [0:7]; reg [31:0] act [0:7];
  always @(posedge clk) if (cfg_we) case (cfg_addr[9:7])
    3'd0: wlo[cfg_addr[2:0]]  <= cfg_wdata[CW-1:0];
    3'd1: whi[cfg_addr[2:0]]  <= cfg_wdata[CW-1:0];
    3'd2: wck[cfg_addr[2:0]] <= cfg_wdata[31:30];
    3'd3: if (cfg_addr[2:0] != 0) pat[cfg_addr[2:0]] <= cfg_wdata[16:0];
    3'd4: kc[cfg_addr[2:0]] <= cfg_wdata[15:0];
    3'd5: act[cfg_addr[2:0]] <= cfg_wdata;
    default: ;
  endcase
  reg [CW-1:0] x [0:2]; reg [CW-1:0] te [0:3];
  reg entry, first; reg [7:0] pprev, pend1, pend2, pev;
  reg [7:0] sr; reg [5:0] bitcnt; reg [31:0] lfsr;
  reg [7:0] txf [0:7]; reg [2:0] txw, txr; reg [3:0] txn;
  reg [7:0] rxf [0:7]; reg [2:0] rxw, rxr;
  assign rx_byte = rxf[rxr];
  wire [13:0] lw = loc_word_in;
  wire [7:0] chg = pins ^ pprev;
  wire [7:0] a1 = first ? pend1 : 8'h00, a2 = first ? pend2 : 8'h00;
  wire [7:0] pend = chg | a1 | a2;
  wire [7:0] evs = pev | ev_in;
  wire [3:0] en; wire [1:0] age [0:3]; wire [CW-1:0] vv [0:3];
  genvar i;
  generate for (i = 0; i < 4; i = i + 1) begin : g
    wire [31:0] e = edge_words[32*i +: 32];
    wire [16:0] p = (e[24:22] == 0) ? 17'd0 : pat[e[24:22]];
    wire [7:0] m = p[7:0];
    wire lvl = ((pins & m) == (p[15:8] & m));
    wire [7:0] trig = pend & m;
    wire pin_ok = (e[24:22] == 0) | (lvl & (~p[16] | |trig));
    assign age[i] = |(trig & chg) ? 2'd0 : |(trig & a1) ? 2'd1 : |(trig & a2) ? 2'd2 : 2'd0;
    wire [2:0] wi = e[21:19];
    wire [CW-1:0] xc = x[wck[wi]];
    assign vv[i] = (xc > age[i]) ? xc - age[i] : 0;
    reg clk_ok, dat_ok;
    wire [15:0] k = kc[e[13:11]];
    always @* begin
      case (e[18:17])
        2'd0: clk_ok = 1'b1;
        2'd1: clk_ok = vv[i] >= wlo[wi];
        2'd2: clk_ok = (vv[i] >= wlo[wi]) & (vv[i] <= whi[wi]);
        default: clk_ok = 1'b0;
      endcase
      case (e[16:14])
        3'd0: dat_ok = 1'b1;
        3'd1: dat_ok = bitcnt == k[5:0];
        3'd2: dat_ok = bitcnt <  k[5:0];
        3'd3: dat_ok = ((sr & k[15:8]) == (k[7:0] & k[15:8]));
        3'd4: dat_ok = evs[e[13:11]];
        3'd5: dat_ok = 1'b0;
        3'd6: dat_ok = 1'b0;
        default: dat_ok = ((sr & k[15:8]) != (k[7:0] & k[15:8]));
      endcase
    end
    assign en[i] = ~entry & e[1] & pin_ok & clk_ok & dat_ok;
  end endgenerate
  wire any = |en;
  wire [1:0] sel = en[0] ? 2'd0 : en[1] ? 2'd1 : en[2] ? 2'd2 : 2'd3;
  wire [31:0] fe = edge_words[32*sel +: 32];
  wire [31:0] fa = act[fe[9:7]];
  wire [16:0] fp = (fe[24:22] == 0) ? 17'd0 : pat[fe[24:22]];
  wire [2:0] iwi = lw[10:8];
  wire tmo = lw[12] & (x[wck[iwi]] > whi[iwi]);
  wire unexp = |(pend & lw[7:0]);
  // policy fire time per slot, computed at entry
  function [CW-1:0] pol(input [CW-1:0] lo, input [CW-1:0] hi, input [CW-1:0] nom, input [19:0] r0);
    reg [CW-1:0] d, mk, r; begin
      d = hi - lo; mk = d | (d>>1) | (d>>2) | (d>>4) | (d>>8) | (d>>16); r = r0 & mk;
      if (r > d) r = r - (d + 1);
      case (policy) 3'd0: pol = nom; 3'd1: pol = lo; 3'd2: pol = hi; 3'd3: pol = lo + r;
        default: pol = (sweep_k > d) ? hi : lo + sweep_k; endcase
    end endfunction
  integer j;
  wire dbit = (fa[23:20] == 4'd5 || fa[23:20] == 4'd6) ? sr[7] : sr[7];
  always @(posedge clk) begin
    if (!rst_n) begin
      loc <= 0; entry <= 1; first <= 0; pprev <= 0; pend1 <= 0; pend2 <= 0; pev <= 0;
      sr <= 0; bitcnt <= 0; lfsr <= 1; pout <= 0; poe <= 0; ev_out <= 0; viol <= 0; cov_stb <= 0; tok_pop <= 0;
      txw <= 0; txr <= 0; txn <= 0; rxw <= 0; rxr <= 0;
      for (j = 0; j < 3; j = j + 1) x[j] <= 0;
    end else begin
      pprev <= pins;
      for (j = 0; j < 3; j = j + 1) x[j] <= (&x[j]) ? x[j] : x[j] + 1'b1;
      ev_out <= 0; cov_stb <= 0; tok_pop <= 0; viol <= 0;
      if (rx_re) rxr <= rxr + 1'b1;
      if (entry) begin
        entry <= 0; first <= 1; pend1 <= chg; pev <= pev | ev_in;

      end else begin
        first <= 0;
        if (any) begin
          loc <= fe[30:25]; entry <= 1;
          pend2 <= pend & ~fp[7:0]; pend1 <= 0; pev <= evs;
          for (j = 0; j < 3; j = j + 1) if (fe[4 + j]) x[j] <= 1 + age[sel];
          if (fa[27]) ev_out[fa[26:24]] <= 1'b1;
          cov_stb <= fe[0];
          cov_word <= {loc, sel, 4'b0, (vv[sel] > wlo[fe[21:19]]) ? vv[sel] - wlo[fe[21:19]] : {CW{1'b0}}};
          case (fa[23:20])
            4'd2: begin rxf[rxw] <= sr; rxw <= rxw + 1'b1; bitcnt <= 0; end
            4'd4: begin sr <= {sr[6:0], pins[fa[19:17]]}; bitcnt <= (&bitcnt) ? bitcnt : bitcnt + 1'b1; end
            4'd8: bitcnt <= 0;
            default: ;
          endcase
        end else begin
          if (unexp | tmo) begin viol <= 1'b1; loc <= 0; entry <= 1; for (j = 0; j < 3; j = j + 1) x[j] <= 1; end
          pend1 <= 0; pend2 <= 0; pev <= 0;
        end
      end
    end
  end
endmodule
