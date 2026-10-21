// Area probe: the configuration tables of ta_engine_v4b (CW=16) alone, with the same read ports (6 window, 5 pattern,
// 4 constant, 1 action reads). Not a design.
module tables(input clk, input cfg_we, input [9:0] cfg_addr, input [31:0] cfg_wdata,
  input [127:0] e, input [3:0] iwi, input [1:0] sel, output [31:0] o);
  reg [15:0] wlo [0:15], whi [0:15], wnom [0:15]; reg [1:0] wck [0:15];
  reg [16:0] pat [1:7]; reg [15:0] kc [0:7]; reg [31:0] act [0:15];
  always @(posedge clk) if (cfg_we) case (cfg_addr[9:7])
    3'd0: wlo[cfg_addr[3:0]]  <= cfg_wdata[15:0];
    3'd1: whi[cfg_addr[3:0]]  <= cfg_wdata[15:0];
    3'd2: begin wnom[cfg_addr[3:0]] <= cfg_wdata[15:0]; wck[cfg_addr[3:0]] <= cfg_wdata[31:30]; end
    3'd3: if (cfg_addr[2:0] != 0) pat[cfg_addr[2:0]] <= cfg_wdata[16:0];
    3'd4: kc[cfg_addr[2:0]] <= cfg_wdata[15:0];
    3'd5: act[cfg_addr[3:0]] <= cfg_wdata;
    default: ;
  endcase
  wire [31:0] acc [0:4];
  genvar i;
  generate for (i = 0; i < 4; i = i + 1) begin : g
    wire [31:0] w = e[32*i +: 32];
    wire [3:0] wi = {w[2], w[21:19]};
    wire [16:0] p = (w[24:22] == 0) ? 17'd0 : pat[w[24:22]];
    assign acc[i+1] = acc[i] ^ {wlo[wi], whi[wi]} ^ {wnom[wi], 14'd0, wck[wi]} ^ {15'd0, p} ^ {16'd0, kc[w[13:11]]};
  end endgenerate
  assign acc[0] = 32'd0;
  wire [31:0] fe = e[32*sel +: 32];
  wire [16:0] fp = (fe[24:22] == 0) ? 17'd0 : pat[fe[24:22]];
  assign o = acc[4] ^ act[fe[10:7]] ^ {whi[iwi], wck[iwi], 14'd0} ^ {15'd0, fp} ^ {wlo[{fe[2], fe[21:19]}], 16'd0};
endmodule
