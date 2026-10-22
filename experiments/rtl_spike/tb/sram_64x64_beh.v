// Behavioural stand-in for RM_IHPSG13_1P_64x64_c2_bm_bist, simulation only: synchronous read and write, DOUT holds
// its last read value (SEMANTICS R4.2, from the PDK functional model). BIST ports ignored.
`default_nettype none
module RM_IHPSG13_1P_64x64_c2_bm_bist (
    input wire A_CLK, input wire A_MEN, input wire A_WEN, input wire A_REN, input wire [5:0] A_ADDR,
    input wire [63:0] A_DIN, input wire A_DLY, output reg [63:0] A_DOUT, input wire [63:0] A_BM,
    input wire A_BIST_CLK, input wire A_BIST_EN, input wire A_BIST_MEN, input wire A_BIST_WEN, input wire A_BIST_REN,
    input wire [5:0] A_BIST_ADDR, input wire [63:0] A_BIST_DIN, input wire [63:0] A_BIST_BM
);
    reg [63:0] mem [0:63];
    always @(posedge A_CLK) begin
        if (A_MEN && A_WEN) mem[A_ADDR] <= (mem[A_ADDR] & ~A_BM) | (A_DIN & A_BM);
        if (A_MEN && A_REN) A_DOUT <= mem[A_ADDR];
    end
endmodule
