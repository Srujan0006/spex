# Standards-derived oracles (independent of spec/)

Write these from the protocol standards only. Do not import anything from `spec/` or `spex/`.

- UART: 8N1 frame decoder and encoder with a baud-tolerance parameter.
- SPI: master and target models for modes 0-3.
- I2C: wired-AND bus model, controller and target behaviour, and the UM10204 timing table (standard and fast mode) as checkable limits.

Each oracle comes with a planted-fault test that it must reject.
