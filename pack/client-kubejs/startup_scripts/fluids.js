StartupEvents.registry('fluid', event => {
    event.create('coolant', "thin")
    .tint(0x70BAEA)
    .noBlock()
    
    event.create('super_coolant', "thick")
    .tint(0x0078D7)
    event.create('kelp_gel', "thick")
    .tint(0x3B4C3A)
    event.create('fine_oil', "thick")
    .tint(0x29190E)
})