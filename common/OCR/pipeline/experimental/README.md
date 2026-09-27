# Optional rendering path

`font_sprite_renderer.py` preserves an alternative glyph and digit-sprite renderer. The frozen v6/v5 recipe uses `core_training_data.render` and `scene_style.raster`; this optional renderer did not produce the reported training images. Promote it to a versioned recipe only after an explicit data comparison and tests.
