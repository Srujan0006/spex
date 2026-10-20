// SPEX week-1 floorplan experiment (not a design): one SRAM macro with dummy logic around it.
// An LFSR drives every functional macro input and a register filler; the macro output and the filler fold
// into one output bit, so synthesis keeps the macro's pins and the filler. BIST inputs are tied off.
`default_nettype none
module fp_tile #(
    parameter AW = 6,
    parameter DW = 64,
    parameter FILL = 64,        // filler registers (multiple of 8)
    parameter SEED = 32'h1
) (
    input  wire clk,
    input  wire rst_n,
    input  wire [7:0] din,
    output reg  dout
);
    reg [31:0] lfsr;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) lfsr <= SEED;
        else lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0] ^ din[0]};

    // replicate the LFSR across DW bits with a per-bit twist so no two inputs are equal
    wire [DW-1:0] wide;
    genvar i;
    generate
        for (i = 0; i < DW; i = i + 1) begin : g_wide
            assign wide[i] = lfsr[i % 32] ^ lfsr[(i * 7 + 3) % 32] ^ din[i % 8];
        end
    endgenerate

    wire [DW-1:0] q;
    generate
        if (DW == 64) begin : g_m64
            RM_IHPSG13_1P_64x64_c2_bm_bist u_sram (
                .A_CLK(clk), .A_MEN(lfsr[0] | lfsr[5]), .A_WEN(lfsr[1]), .A_REN(~lfsr[1]),
                .A_ADDR(lfsr[AW+1:2]), .A_DIN(wide), .A_DLY(1'b1), .A_DOUT(q), .A_BM(~wide ^ {DW{lfsr[9]}}),
                .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0), .A_BIST_REN(1'b0),
                .A_BIST_ADDR({AW{1'b0}}), .A_BIST_DIN({DW{1'b0}}), .A_BIST_BM({DW{1'b0}}));
        end else begin : g_m32
            RM_IHPSG13_1P_256x32_c2_bm_bist u_sram (
                .A_CLK(clk), .A_MEN(lfsr[0] | lfsr[5]), .A_WEN(lfsr[1]), .A_REN(~lfsr[1]),
                .A_ADDR(lfsr[AW+1:2]), .A_DIN(wide), .A_DLY(1'b1), .A_DOUT(q), .A_BM(~wide ^ {DW{lfsr[9]}}),
                .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0), .A_BIST_REN(1'b0),
                .A_BIST_ADDR({AW{1'b0}}), .A_BIST_DIN({DW{1'b0}}), .A_BIST_BM({DW{1'b0}}));
        end
    endgenerate

    // filler: FILL registers in 8-bit lanes, each lane a shift register mixed with the macro output
    reg [FILL-1:0] fill;
    reg [DW-1:0] qr;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) begin
            fill <= {FILL{1'b0}};
            qr <= {DW{1'b0}};
            dout <= 1'b0;
        end else begin
            qr <= q;
            fill <= {fill[FILL-9:0], fill[FILL-1:FILL-8] ^ qr[7:0] ^ qr[DW-1:DW-8] ^ din};
            dout <= ^fill ^ ^qr;
        end
endmodule
