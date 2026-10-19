// Area probe v2 (review fixes). Not a design.
// - independent pin / clock / data guard fields, ANDed (Con 1)
// - clock op includes the closed window lo <= x <= hi (Check role)
// - 8-entry tables instead of 16 (Con 6)
// - per-location watch mask: a watched pin change that enables no edge is an
//   immediate UNEXPECTED violation, so Check needs no per-edge error edges (Con 3)
// - edge words arrive one cycle after loc changes (4 parallel 32-bit macros, E=1);
//   pin changes during that cycle are kept as sticky flags with a timestamp (Con 2)
// - coverage record is a 32-bit word pushed to an external queue (Con 5)
module ta_engine_v3 #(parameter CW = 20)(
  input             clk, rst_n,
  input      [7:0]  pins,
  input      [7:0]  ev_in,
  input      [7:0]  choice,        // host transaction stream token (choice points)
  input             choice_valid,
  output reg        choice_pop,
  input      [255:0] edge_words,   // 4 x 64-bit inline edges of current location
  input      [15:0] loc_word,      // {inv_en, inv_win[2:0], 4'b0, watch_mask[7:0]}
  output reg [6:0]  loc,
  output reg [7:0]  pout, poe, ev_out,
  output reg        viol_timeout, viol_unexpected,
  output reg        cov_stb,
  output reg [31:0] cov_word,      // {loc[6:0], edge[1:0], 3'b0, offset[19:0]}
  input             cfg_we, input [5:0] cfg_addr, input [31:0] cfg_wdata,
  input      [1:0]  policy, input [CW-1:0] sweep_k, input monitor,
  input             tx_we, input [7:0] tx_byte, input rx_re, output [7:0] rx_byte, output rx_empty
);
  reg [17:0]   pat [0:7];                 // {mode, val, mask}
  reg [2*CW+1:0] win [0:7];               // {sel[1:0], hi, lo}
  reg [5:0]    kt  [0:7];
  reg [31:0]   act [0:15];
  reg [31:0]   dcmp_val, dcmp_mask; reg [15:0] crc_poly;
  always @(posedge clk) if (cfg_we) case (cfg_addr[5:4])
    2'd0: if (!cfg_addr[3]) pat[cfg_addr[2:0]] <= cfg_wdata[17:0]; else kt[cfg_addr[2:0]] <= cfg_wdata[5:0];
    2'd1: if (!cfg_addr[3]) win[cfg_addr[2:0]][CW-1:0] <= cfg_wdata[CW-1:0];
          else win[cfg_addr[2:0]][2*CW+1:CW] <= {cfg_wdata[31:30], cfg_wdata[CW-1:0]};
    2'd2: act[cfg_addr[3:0]] <= cfg_wdata;
    2'd3: case (cfg_addr[1:0]) 0: dcmp_val <= cfg_wdata; 1: dcmp_mask <= cfg_wdata; 2: crc_poly <= cfg_wdata[15:0]; default: ; endcase
  endcase

  reg [CW-1:0] x0, x1, x2, fire_t, t_first;
  reg          valid;
  reg [7:0]    pins_prev, sticky;
  reg [31:0]   sh; reg [5:0] bitcnt; reg [15:0] crc, lfsr;
  reg [7:0] txf [0:7]; reg [2:0] txw, txr; reg [3:0] txn;
  reg [7:0] rxf [0:7]; reg [2:0] rxw, rxr; reg [3:0] rxn;
  assign rx_byte = rxf[rxr]; assign rx_empty = (rxn == 0);
  function [CW-1:0] xsel(input [1:0] s); xsel = s==0 ? x0 : s==1 ? x1 : x2; endfunction

  wire [7:0] chg = (pins ^ pins_prev) | sticky;   // includes changes seen during entry
  wire [3:0] en;
  genvar i;
  generate for (i = 0; i < 4; i = i + 1) begin : g
    // 64-bit inline edge: [63:57] tgt [56:49] pmask [48:41] pval [40] pmode [39:38] csel
    // [37:36] cop [35:25] lo [24:14] hi [13:11] dop [10:5] k [4:1] act [0] valid
    wire [63:0] e = edge_words[64*i +: 64];
    wire pm_now  = ((pins      & e[56:49]) == (e[48:41] & e[56:49]));
    wire pm_prev = ((pins_prev & e[56:49]) == (e[48:41] & e[56:49]));
    wire pin_ok  = (e[56:49] == 0) | (e[40] ? (pm_now & (~pm_prev | |(sticky & e[56:49]))) : pm_now);
    wire [CW-1:0] xv = xsel(e[39:38]);
    wire [CW-1:0] lo = {{(CW-11){1'b0}}, e[35:25]}, hi = {{(CW-11){1'b0}}, e[24:14]};
    reg clk_ok, dat_ok;
    always @* begin
      case (e[37:36])
        2'd0: clk_ok = 1'b1;
        2'd1: clk_ok = xv >= lo;
        2'd2: clk_ok = (xv >= lo) & (xv <= hi);
        default: clk_ok = (xv == fire_t);
      endcase
      case (e[13:11])
        3'd0: dat_ok = 1'b1;
        3'd1: dat_ok = bitcnt == e[10:5];
        3'd2: dat_ok = bitcnt <  e[10:5];
        3'd3: dat_ok = ((sh & dcmp_mask) == (dcmp_val & dcmp_mask));
        3'd4: dat_ok = ev_in[e[7:5]];
        3'd5: dat_ok = (txn != 0);
        3'd6: dat_ok = choice_valid & (choice[5:0] == e[10:5]);
        default: dat_ok = 1'b0;
      endcase
    end
    assign en[i] = valid & e[0] & pin_ok & clk_ok & dat_ok;
  end endgenerate

  wire       any = |en;
  wire [1:0] sel = en[0] ? 2'd0 : en[1] ? 2'd1 : en[2] ? 2'd2 : 2'd3;
  wire [63:0] fe = edge_words[64*sel +: 64];
  wire [31:0] fa = act[fe[4:1]];
  wire [2*CW+1:0] iw = win[loc_word[14:12]];
  wire inv_bad = valid & loc_word[15] & (xsel(iw[2*CW+1:2*CW]) > iw[2*CW-1:CW]);
  wire unexpected = valid & monitor & |(chg & loc_word[7:0]) & ~any;

  wire [CW-1:0] lo0 = {{(CW-11){1'b0}}, edge_words[35:25]}, hi0 = {{(CW-11){1'b0}}, edge_words[24:14]}, span = hi0 - lo0;
  wire [CW-1:0] smear = span | (span>>1) | (span>>2) | (span>>4) | (span>>8) | (span>>16);
  wire [CW-1:0] roff = {{(CW-16){1'b0}}, lfsr} & smear;
  wire [CW-1:0] ft = policy==0 ? lo0 : policy==1 ? hi0 :
                     policy==2 ? ((roff > span) ? lo0 + (roff - span) : lo0 + roff) :
                     ((sweep_k > span) ? hi0 : lo0 + sweep_k);
  wire crc_fb = crc[15] ^ sh[0];

  always @(posedge clk) begin
    if (!rst_n) begin
      loc <= 0; valid <= 0; x0 <= 0; x1 <= 0; x2 <= 0; pout <= 0; poe <= 0; ev_out <= 0;
      viol_timeout <= 0; viol_unexpected <= 0; cov_stb <= 0; lfsr <= 16'hACE1; sh <= 0; bitcnt <= 0;
      crc <= 16'hFFFF; txw <= 0; txr <= 0; txn <= 0; rxw <= 0; rxr <= 0; rxn <= 0; pins_prev <= 0;
      fire_t <= 0; sticky <= 0; t_first <= 0; choice_pop <= 0;
    end else begin
      pins_prev <= pins;
      lfsr <= {lfsr[14:0], lfsr[15]^lfsr[13]^lfsr[12]^lfsr[10]};
      x0 <= x0 + 1'b1; x1 <= x1 + 1'b1; x2 <= x2 + 1'b1;
      ev_out <= 0; cov_stb <= 0; choice_pop <= 0;
      viol_timeout <= inv_bad & ~any; viol_unexpected <= unexpected;
      if (!valid) begin
        valid <= 1'b1; fire_t <= ft;
        sticky <= sticky | (pins ^ pins_prev);                    // remember entry-cycle edges
        if (|(pins ^ pins_prev) && sticky == 0) t_first <= x0;      // and when the first one happened
      end else sticky <= 0;
      if (tx_we && txn != 8) begin txf[txw] <= tx_byte; txw <= txw + 1'b1; end
      if (rx_re && rxn != 0) rxr <= rxr + 1'b1;
      if (any) begin
        loc <= fe[63:57]; valid <= 1'b0;
        if (fa[28]) x0 <= 0; if (fa[29]) x1 <= 0; if (fa[30]) x2 <= 0;
        if (!monitor) begin
          if (fa[16]) poe <= (poe & ~fa[7:0]) | (fa[15:8] & fa[7:0]);
          else        pout <= (pout & ~fa[7:0]) | (fa[15:8] & fa[7:0]);
        end
        if (fa[24]) ev_out[fa[23:21]] <= 1'b1;
        if (fe[13:11] == 3'd6) choice_pop <= 1'b1;
        cov_stb  <= fa[31];
        cov_word <= {loc, sel, 3'b0, (|sticky ? t_first : x0) - lo0};  // offset from window start
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
      txn <= txn + ((tx_we && txn != 8) ? 1 : 0) - ((any && fa[20:17]==4'd3 && txn != 0) ? 1 : 0);
      if (any && fa[20:17]==4'd3 && txn != 0) txr <= txr + 1'b1;
      rxn <= rxn + ((any && fa[20:17]==4'd4) ? 1 : 0) - ((rx_re && rxn != 0) ? 1 : 0);
    end
  end
endmodule
