// Port-only blackbox of the IHP SRAM macro RM_IHPSG13_1P_64x16_c2 (ports from IHP-Open-PDK
// 2bbec755 ihp-sg13g2/libs.ref/sg13g2_sram/verilog/RM_IHPSG13_1P_64x16_c2.v). The macro itself comes in through
// MACROS in config.json; this file is the MACROS "nl" model and is not a source file.
/* verilator lint_off UNDRIVEN */
/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module RM_IHPSG13_1P_64x16_c2 (
    input A_CLK, input A_MEN, input A_WEN, input A_REN,
    input [5:0] A_ADDR, input [15:0] A_DIN, input A_DLY,
    output [15:0] A_DOUT
);
endmodule
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on UNDRIVEN */
