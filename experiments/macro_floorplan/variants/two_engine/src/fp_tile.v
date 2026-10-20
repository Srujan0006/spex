// SPEX floorplan experiment (not a design): one IHP SRAM macro with dummy logic shaped like an engine.
// An LFSR drives every functional macro input; the filler is a register table of TW 8-bit words written from the
// macro output and read through 4 LFSR-addressed read ports (flops plus mux trees, the mix of the measured engine
// probes: about 40% sequential, mostly mux2/mux4 otherwise); everything folds into one output bit so synthesis keeps
// it. BIST inputs (bm_bist macros) are tied off. KIND: 0 = 1P_64x64_bm_bist, 1 = 1P_256x32_bm_bist, 2 = 1P_64x16.
`default_nettype none
module fp_tile #(
    parameter KIND = 0,
    parameter TW = 16,          // filler table words (8 bits each), a power of two >= 4
    parameter SEED = 32'h1
) (
    input  wire clk,
    input  wire rst_n,
    input  wire [7:0] din,
    output reg  dout
);
    localparam AW = (KIND == 1) ? 8 : 6;
    localparam DW = (KIND == 0) ? 64 : (KIND == 1) ? 32 : 16;
    localparam TA = $clog2(TW);

    reg [31:0] lfsr;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) lfsr <= SEED;
        else lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0] ^ din[0]};

    wire [DW-1:0] wide;
    genvar i;
    generate
        for (i = 0; i < DW; i = i + 1) begin : g_wide
            assign wide[i] = lfsr[i % 32] ^ lfsr[(i * 7 + 3) % 32] ^ din[i % 8];
        end
    endgenerate

    wire [DW-1:0] q;
    wire men = lfsr[0] | lfsr[5], wen = lfsr[1], ren = ~lfsr[1];
    wire [AW-1:0] addr = lfsr[AW+1:2];
    wire [DW-1:0] bm = ~wide ^ {DW{lfsr[9]}};
    generate
        if (KIND == 0) begin : g_m64
            RM_IHPSG13_1P_64x64_c2_bm_bist u_sram (
                .A_CLK(clk), .A_MEN(men), .A_WEN(wen), .A_REN(ren), .A_ADDR(addr), .A_DIN(wide), .A_DLY(1'b1),
                .A_DOUT(q), .A_BM(bm), .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0),
                .A_BIST_REN(1'b0), .A_BIST_ADDR({AW{1'b0}}), .A_BIST_DIN({DW{1'b0}}), .A_BIST_BM({DW{1'b0}}));
        end else if (KIND == 1) begin : g_m32
            RM_IHPSG13_1P_256x32_c2_bm_bist u_sram (
                .A_CLK(clk), .A_MEN(men), .A_WEN(wen), .A_REN(ren), .A_ADDR(addr), .A_DIN(wide), .A_DLY(1'b1),
                .A_DOUT(q), .A_BM(bm), .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0),
                .A_BIST_REN(1'b0), .A_BIST_ADDR({AW{1'b0}}), .A_BIST_DIN({DW{1'b0}}), .A_BIST_BM({DW{1'b0}}));
        end else begin : g_m16
            RM_IHPSG13_1P_64x16_c2 u_sram (
                .A_CLK(clk), .A_MEN(men), .A_WEN(wen), .A_REN(ren), .A_ADDR(addr), .A_DIN(wide), .A_DLY(1'b1),
                .A_DOUT(q));
            wire _unused_bm = &{bm, 1'b0};     // the 64x16 macro has no bit mask
        end
    endgenerate

    reg [DW-1:0] qr;
    reg [7:0] tbl [0:TW-1];
    wire [7:0] r0 = tbl[lfsr[TA+3:4]], r1 = tbl[lfsr[TA+9:10]], r2 = tbl[lfsr[TA+15:16]] , r3 = tbl[din[TA-1:0] ^ qr[TA-1:0]];
    always @(posedge clk) tbl[lfsr[TA+20:21]] <= qr[7:0] ^ qr[DW-1:DW-8] ^ din ^ r3;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) begin
            qr <= {DW{1'b0}};
            dout <= 1'b0;
        end else begin
            qr <= q;
            dout <= ^(r0 ^ r1 ^ r2) ^ ^qr;
        end
endmodule
