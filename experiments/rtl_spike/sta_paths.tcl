# Per-path post-route timing of the RTL spike (owner task 4, 2026-10-22). Run with OpenROAD from the repo root after
# the harden, once per corner:  CORNER=slow|typ|fast openroad -exit -no_splash experiments/rtl_spike/sta_paths.tcl
#   (A) the edge/location macros' clock-to-output through the table reads into the per-slot registers
#   (B) the per-slot registers through guards, priority and next location into the macros' address / enable pins
#   (action) the fired slot through the action table into the pin-write registers (uio_out / uio_oe)
set pdk $::env(PDK_ROOT)/ihp-sg13cmos5l/libs.ref
array set std  {slow slow_1p08V_125C typ typ_1p20V_25C fast fast_1p32V_m40C}
array set sram {slow slow_1p08V_125C typ typ_1p20V_25C fast fast_1p32V_m55C}
set c $::env(CORNER)
read_liberty $pdk/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_$std($c).lib
read_liberty $pdk/sg13cmos5l_sram/lib/RM_IHPSG13_1P_64x64_c2_bm_bist_$sram($c).lib
read_liberty $pdk/sg13cmos5l_sram/lib/RM_IHPSG13_1P_64x16_c2_$sram($c).lib
read_db [lindex [glob runs/wokwi/final/odb/*.odb] 0]
set spef [glob -nocomplain runs/wokwi/final/spef/nom*/*.spef]
if {[llength $spef]} { read_spef [lindex $spef 0] } else { puts "WARNING: no nom SPEF, wire load only" }
read_sdc [lindex [glob runs/wokwi/final/sdc/*.sdc] 0]
set_propagated_clock [all_clocks]

set macros [get_cells {u_m0 u_m1 u_loc}]
set fields {slew cap fanout}
puts "\n==================== corner $c: (A) macro clock-to-output -> table reads -> slot registers"
report_checks -from $macros -path_delay max -fields $fields -digits 3
puts "\n==================== corner $c: (B) slot registers -> guards -> priority -> next address -> macro inputs"
report_checks -to $macros -path_delay max -fields $fields -digits 3
puts "\n==================== corner $c: (action) fired slot -> action table -> pin-write registers"
set drivers {}
foreach port [get_ports {uio_out[*] uio_oe[*]}] {
    foreach pin [get_pins -of_objects [get_nets -of_objects $port] -filter "direction == output"] {
        lappend drivers [get_cells -of_objects $pin]
    }
}
if {[llength $drivers]} {
    report_checks -to $drivers -path_delay max -fields $fields -digits 3
} else {
    puts "no pin-write registers found on uio_out / uio_oe"
}
puts "\n==================== corner $c: summary"
report_wns
report_tns
report_check_types -max_slew -max_capacitance -max_fanout -violators
