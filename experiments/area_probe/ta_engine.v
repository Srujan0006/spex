// Area-probe sketch of ONE timed-automaton engine context. Not a design:
// enough logic to size the idea on sg13cmos5l. The edge memory (4 x 32-bit
// edge slots per location) is an SRAM macro outside this module: edge_words
// arrives one cycle after loc changes (registered read).
module ta_engine #(
  parameter CW = 20            // clock width
)(
  input             clk, rst_n,
  input      [7:0]  pins,       // synchronised pin inputs
  input      [7:0]  ev_in,      // broadcast events from other engines
  input      [127:0] edge_words,// 4 edges of current location (from SRAM)
  input      [31:0] inv_word,   // location invariant word (from SRAM)
  output reg [6:0]  loc,        // SRAM read address
  output reg [7:0]  pout, poe,
  output reg [7:0]  ev_out,
  output reg        violation,
  output reg        log_stb,
  output reg [8:0]  log_edge,   // {loc, edge idx} for trace / coverage RMW
  // host config writes
  input             cfg_we,
  input      [5:0]  cfg_addr,
  input      [31:0] cfg_wdata,
  input      [1:0]  policy,     // 0 earliest 1 latest 2 random 3 sweep
  input      [CW-1:0] sweep_k,
  input             monitor,    // 1 = never drive pins
  // host data FIFOs (byte)
  input             tx_we, input [7:0] tx_byte, input rx_re, output [7:0] rx_byte,
  output            rx_empty
);
  // ---- tables (flops) ----
  reg [17:0] pat   [0:15];   // {mode[1:0], val[7:0], mask[7:0]}
  reg [CW-1:0] cst [0:15];
  reg [31:0] act   [0:15];
  reg [31:0] dcmp_val, dcmp_mask;
  reg [15:0] crc_poly;
  always @(posedge clk) if (cfg_we) begin
    case (cfg_addr[5:4])
      2'd0: pat[cfg_addr[3:0]] <= cfg_wdata[17:0];
      2'd1: cst[cfg_addr[3:0]] <= cfg_wdata[CW-1:0];
      2'd2: act[cfg_addr[3:0]] <= cfg_wdata;
      2'd3: case (cfg_addr[1:0]) 0: dcmp_val <= cfg_wdata; 1: dcmp_mask <= cfg_wdata;
                                 2: crc_poly <= cfg_wdata[15:0]; default: ; endcase
    endcase
  end
  // ---- state ----
  reg [CW-1:0] x0, x1, x2;
  reg [CW-1:0] fire_t;
  reg          valid;          // edge words valid for current loc
  reg [7:0]    pins_prev;
  reg [31:0]   sh; reg [5:0] bitcnt; reg [15:0] crc; reg [15:0] lfsr;
  // tiny FIFOs
  reg [7:0] txf [0:7]; reg [2:0] txw, txr; reg [3:0] txn;
  reg [7:0] rxf [0:7]; reg [2:0] rxw, rxr; reg [3:0] rxn;
  assign rx_byte = rxf[rxr]; assign rx_empty = (rxn == 0);

  // ---- guard evaluation, 4 edges in parallel ----
  function [CW-1:0] xsel(input [1:0] s); xsel = s==0 ? x0 : s==1 ? x1 : x2; endfunction
  wire [3:0] en;
  genvar i;
  generate for (i = 0; i < 4; i = i + 1) begin : g
    wire [31:0] e   = edge_words[32*i +: 32];
    wire [17:0] p   = pat[e[24:21]];
    wire pm_now  = ((pins & p[7:0]) == (p[15:8] & p[7:0]));
    wire pm_prev = ((pins_prev & p[7:0]) == (p[15:8] & p[7:0]));
    wire pin_ok  = (e[24:21] == 0) ? 1'b1 : (p[17:16] == 2'd1) ? (pm_now & ~pm_prev) : pm_now;
    wire [CW-1:0] xv = xsel(e[20:19]);
    wire [CW-1:0] c  = cst[e[15:12]];
    reg  clk_ok;
    always @* case (e[18:16])
      3'd0: clk_ok = (e[20:19] == 2'd3) | (xv >= c);
      3'd1: clk_ok = xv < c;
      3'd2: clk_ok = xv == c;
      3'd3: clk_ok = xv == fire_t;
      3'd4: clk_ok = ((sh & dcmp_mask) == (dcmp_val & dcmp_mask));
      3'd5: clk_ok = ev_in[e[4:2]];
      3'd6: clk_ok = bitcnt == c[5:0];
      default: clk_ok = 1'b0;
    endcase
    assign en[i] = valid & e[1] & pin_ok & clk_ok;
  end endgenerate

  wire       any = |en;
  wire [1:0] sel = en[0] ? 2'd0 : en[1] ? 2'd1 : en[2] ? 2'd2 : 2'd3;
  wire [31:0] fe = edge_words[32*sel +: 32];
  wire [31:0] fa = act[fe[11:8]];

  // invariant: {en, clk sel[1:0], const idx[3:0]}
  wire inv_bad = valid & inv_word[6] & (xsel(inv_word[5:4]) > cst[inv_word[3:0]]);

  // policy fire time for the location's policy edge (edge slot 0 by convention)
  wire [CW-1:0] lo = cst[edge_words[15:12]];
  wire [CW-1:0] hi = cst[edge_words[15:12] + 4'd1];
  wire [CW-1:0] span = hi - lo;
  wire [CW-1:0] smear = span | (span>>1) | (span>>2) | (span>>4) | (span>>8) | (span>>16);
  wire [CW-1:0] roff  = {{(CW-16){1'b0}}, lfsr} & smear;
  wire [CW-1:0] ft = policy==0 ? lo : policy==1 ? hi :
                     policy==2 ? ((roff > span) ? lo + (roff - span) : lo + roff) :
                     ((sweep_k > span) ? hi : lo + sweep_k);

  wire crc_fb = crc[15] ^ sh[0];

  always @(posedge clk) begin
    if (!rst_n) begin
      loc <= 0; valid <= 0; x0 <= 0; x1 <= 0; x2 <= 0; pout <= 0; poe <= 0;
      ev_out <= 0; violation <= 0; log_stb <= 0; lfsr <= 16'hACE1; sh <= 0;
      bitcnt <= 0; crc <= 16'hFFFF; txw <= 0; txr <= 0; txn <= 0; rxw <= 0; rxr <= 0; rxn <= 0;
      pins_prev <= 0; fire_t <= 0;
    end else begin
      pins_prev <= pins;
      lfsr <= {lfsr[14:0], lfsr[15]^lfsr[13]^lfsr[12]^lfsr[10]};
      x0 <= x0 + 1'b1; x1 <= x1 + 1'b1; x2 <= x2 + 1'b1;
      ev_out <= 0; log_stb <= 0; violation <= inv_bad & ~any;
      if (!valid) begin valid <= 1'b1; fire_t <= ft; end   // edge words arrive
      if (tx_we && txn != 8) begin txf[txw] <= tx_byte; txw <= txw + 1'b1; end
      if (rx_re && rxn != 0) rxr <= rxr + 1'b1;
      if (any) begin
        loc <= fe[31:25]; valid <= 1'b0;
        if (fe[5]) x0 <= 0; if (fe[6]) x1 <= 0; if (fe[7]) x2 <= 0;
        if (!monitor) begin
          if (fa[16]) poe  <= (poe  & ~fa[7:0]) | (fa[15:8] & fa[7:0]);
          else        pout <= (pout & ~fa[7:0]) | (fa[15:8] & fa[7:0]);
        end
        if (fa[24]) ev_out[fa[23:21]] <= 1'b1;
        log_stb <= fe[0]; log_edge <= {loc, sel};
        case (fa[20:17])
          4'd1: begin sh <= {pins[fa[27:25]], sh[31:1]}; bitcnt <= bitcnt + 1'b1; end
          4'd2: begin if (!monitor) pout[fa[27:25]] <= sh[0]; sh <= {1'b0, sh[31:1]}; bitcnt <= bitcnt + 1'b1; end
          4'd3: begin sh <= {24'd0, txf[txr]}; bitcnt <= 0; end
          4'd4: begin rxf[rxw] <= sh[31:24]; rxw <= rxw + 1'b1; end
          4'd5: crc <= {crc[14:0], 1'b0} ^ (crc_fb ? crc_poly : 16'd0);
          4'd6: bitcnt <= 0;
          4'd7: crc <= 16'hFFFF;
          default: ;
        endcase
      end
      // FIFO counts
      txn <= txn + ((tx_we && txn != 8) ? 1 : 0) - ((any && fa[20:17]==4'd3 && txn != 0) ? 1 : 0);
      if (any && fa[20:17]==4'd3 && txn != 0) txr <= txr + 1'b1;
      rxn <= rxn + ((any && fa[20:17]==4'd4) ? 1 : 0) - ((rx_re && rxn != 0) ? 1 : 0);
    end
  end
endmodule
