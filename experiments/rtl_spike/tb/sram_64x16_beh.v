// Behavioural stand-in for RM_IHPSG13_1P_64x16_c2, simulation only (same read/write/hold behaviour as the 64x64).
`default_nettype none
module RM_IHPSG13_1P_64x16_c2 (
    input wire A_CLK, input wire A_MEN, input wire A_WEN, input wire A_REN, input wire [5:0] A_ADDR,
    input wire [15:0] A_DIN, input wire A_DLY, output reg [15:0] A_DOUT
);
    reg [15:0] mem [0:63];
    always @(posedge A_CLK) begin
        if (A_MEN && A_WEN) mem[A_ADDR] <= A_DIN;
        if (A_MEN && A_REN) A_DOUT <= mem[A_ADDR];
    end
endmodule
