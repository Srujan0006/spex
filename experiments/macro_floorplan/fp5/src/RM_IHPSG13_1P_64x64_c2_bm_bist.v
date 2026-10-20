// Port-only blackbox of the IHP SRAM macro RM_IHPSG13_1P_64x64_c2_bm_bist (ports from IHP-Open-PDK
// 2bbec755 ihp-sg13g2/libs.ref/sg13g2_sram/verilog/RM_IHPSG13_1P_64x64_c2_bm_bist.v). The macro itself comes in through
// MACROS in config.json; this file is the MACROS "nl" model and is not a source file.
/* verilator lint_off UNDRIVEN */
/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module RM_IHPSG13_1P_64x64_c2_bm_bist (
    input A_CLK, input A_MEN, input A_WEN, input A_REN,
    input [5:0] A_ADDR, input [63:0] A_DIN, input A_DLY,
    output [63:0] A_DOUT, input [63:0] A_BM,
    input A_BIST_CLK, input A_BIST_EN, input A_BIST_MEN, input A_BIST_WEN, input A_BIST_REN,
    input [5:0] A_BIST_ADDR, input [63:0] A_BIST_DIN, input [63:0] A_BIST_BM
);
endmodule
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on UNDRIVEN */
