// Smoke tests of the timing spike v2 (entry-cycle slot registers, clock history, actions, violations).
//  1. loop: 0 -(x0 >= 5, action: pin 0 := 1 PP)-> 1 -(pin 0 rises)-> 0 -> 1 ... and uio_oe[0] / uio_out[0] = 1
//  2. clock history: x_d1 = max(x - 1, 0) and x_d2 = max(x - 2, 0) in every cycle, for every clock
//  3. TIMEOUT: location 2 with invariant x0 <= 4 and no enabled edge -> a violation and resync to location 0
`timescale 1ns/1ps
`default_nettype none
module tb_spike;
    reg clk = 0, rst_n = 0;
    reg [7:0] ui = 0, uio = 0;
    wire [7:0] uo, uio_out, uio_oe;
    always #10 clk = ~clk;
    tt_um_srujan0006_spike dut (.ui_in(ui), .uo_out(uo), .uio_in(uio), .uio_out(uio_out), .uio_oe(uio_oe),
                                .ena(1'b1), .clk(clk), .rst_n(rst_n));
    localparam OPAT = 16*34, OK = OPAT + 8*17, OACT = OK + 8*16, OTX = OACT + 16*32, ODRV = OTX + 8;
    // edge word (R11.1): target[30:25] pattern[24:22] window[21:19] ck[18:17] dk[16:14] k[13:11] action[10:7]
    //                    reset[6:4] error[3] winmsb[2] valid[1] log[0]
    function [31:0] edgew(input [5:0] tgt, input [2:0] pat, input [2:0] win, input [1:0] ck, input [3:0] a,
                          input [2:0] rst);
        edgew = {1'b0, tgt, pat, win, ck, 3'd0, 3'd0, a, rst, 1'b0, 1'b0, 1'b1, 1'b0};
    endfunction
    integer n, c, fires, errors, viols, aged, seed;
    reg [5:0] trace [0:15];
    task automatic check_history;
        for (c = 0; c < 3; c = c + 1) begin
            if (dut.u_core.d1[c] !== ((dut.u_core.x[c] > 0) ? dut.u_core.x[c] - 1 : 0) ||
                dut.u_core.d2[c] !== ((dut.u_core.x[c] > 1) ? dut.u_core.x[c] - 2 : 0)) begin
                errors = errors + 1;
                if (errors < 5) $display("history mismatch clock %0d: x %0d d1 %0d d2 %0d", c, dut.u_core.x[c],
                                          dut.u_core.d1[c], dut.u_core.d2[c]);
            end
        end
    endtask
    initial begin
        errors = 0; seed = 12345;
        dut.u_core.cfg = 0;
        dut.u_core.cfg[1*34 +: 34] = {2'd0, 16'd20, 16'd5};               // window 1: clk 0, [5, 20]
        dut.u_core.cfg[2*34 +: 34] = {2'd0, 16'd4, 16'd0};                // window 2: clk 0, hi 4 (invariant)
        dut.u_core.cfg[OPAT + 1*17 +: 17] = {1'b1, 8'h01, 8'h01};          // pattern 1: EDGE, pin 0 = 1
        dut.u_core.cfg[OACT + 1*32 +: 32] = {16'd0, 8'h01, 8'h01};         // action 1: PP pin 0 := 1
        dut.u_core.cfg[ODRV] = 1'b1;                                       // drive_en
        dut.u_m0.mem[0] = {32'd0, edgew(6'd1, 3'd0, 3'd1, 2'd1, 4'd1, 3'b001)};   // loc 0: GE x0 >= 5, act 1
        dut.u_m1.mem[0] = 64'd0;
        dut.u_m0.mem[1] = {32'd0, edgew(6'd0, 3'd1, 3'd0, 2'd0, 4'd0, 3'b010)};   // loc 1: pin 0 rises, reset x1
        dut.u_m1.mem[1] = 64'd0;
        dut.u_m0.mem[2] = 64'd0;  dut.u_m1.mem[2] = 64'd0;                // loc 2: no edges
        dut.u_loc.mem[0] = 16'h0000; dut.u_loc.mem[1] = 16'h0000;
        dut.u_loc.mem[2] = {2'b00, 1'b0, 1'b1, 4'd2, 8'h00};                // loc 2: invariant on window 2
        repeat (3) @(posedge clk);
        rst_n = 1;
        @(negedge clk) ui[2] = 1;
        @(negedge clk) ui[2] = 0;
        @(negedge clk);
        dut.u_core.x[2] = 16'hFFF0; dut.u_core.d1[2] = 16'hFFEF; dut.u_core.d2[2] = 16'hFFEE;   // saturate clock 2
        fires = 0; aged = 0;
        for (n = 0; n < 400; n = n + 1) begin
            @(negedge clk);
            check_history;
            if (($random(seed) & 3) == 0) uio[0] = ~uio[0];                  // random toggles: some land in entry or firing cycles
            if (dut.u_core.any && dut.u_core.ra != 0) aged = aged + 1;
            if (dut.u_core.fired && fires < 16) begin trace[fires] = dut.u_core.loc; fires = fires + 1; end
        end
        if (aged == 0) begin $display("FAIL: no reset with a nonzero age"); $fatal(1); end
        if (dut.u_core.x[2] !== 16'hFFFF) begin $display("FAIL: clock 2 did not saturate"); $fatal(1); end
        if (fires < 4) begin $display("FAIL: only %0d firings", fires); $fatal(1); end
        for (n = 0; n < fires; n = n + 1)
            if (trace[n] != ((n % 2 == 0) ? 6'd1 : 6'd0)) begin $display("FAIL: firing %0d went to %0d", n, trace[n]); $fatal(1); end
        if (uio_oe[0] !== 1'b1 || uio_out[0] !== 1'b1) begin $display("FAIL: action did not drive pin 0"); $fatal(1); end
        // TIMEOUT: retarget location 0 to location 2, which has an invariant x0 <= 4 and no edge
        dut.u_m0.mem[0] = {32'd0, edgew(6'd2, 3'd0, 3'd1, 2'd1, 4'd0, 3'b001)};
        viols = 0;
        for (n = 0; n < 120; n = n + 1) begin
            @(negedge clk);
            check_history;
            uio[0] = (n % 20) >= 10;
            if (dut.u_core.viol) viols = viols + 1;
        end
        if (viols == 0) begin $display("FAIL: no TIMEOUT violation"); $fatal(1); end
        if (errors) begin $display("FAIL: %0d clock history mismatches", errors); $fatal(1); end
        $display("PASS: %0d firings alternating 1, 0; %0d resets with age > 0; clock 2 saturated; action drove pin 0; %0d TIMEOUT violations; history ok", fires, aged, viols);
        $finish;
    end
endmodule
