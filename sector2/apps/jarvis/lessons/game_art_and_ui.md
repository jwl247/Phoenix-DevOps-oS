# Game art and game UI (for the game, Sacrifice)

## HUD and game UI basics
Show only what the player needs right now; hide the rest until it matters. Put critical info (health, ammo, objective, minimap) in the corners and edges, away from the center where the action is. Keep the same thing in the same place every time. Use icons plus numbers rather than long text. Diegetic UI lives inside the game world (a watch on the wrist, a screen in a vehicle); non-diegetic UI floats over the screen; diegetic feels immersive, non-diegetic reads faster.

## Readability at a glance (strategy and military games)
Friend and foe must be told apart instantly: use team colors plus a second cue (shape, outline or icon), never color alone. About 1 in 12 men is colorblind: avoid red-versus-green as the only difference; blue versus orange works for most people. Units should be readable by silhouette from the strategy camera height. Selected units get a clear outline or ring. Important alerts get both a sound and a screen cue.

## Maps and terrain readability
Players should recognize places by landmarks (a tower, a bridge, a river bend). Roads and paths should read clearly against terrain. Use lighting and color value (light vs dark) to guide the eye toward objectives. Keep the minimap simple: terrain in muted colors, units and objectives in bright ones.

## Sprites, textures and pixel art
Texture sizes in powers of two (256, 512, 1024, 2048) work best with game engines and compression. Pack many small images into one texture atlas to draw faster. Pixel art: pick a fixed palette, keep a consistent pixel scale, and scale up only by whole numbers (2x, 3x) with nearest-neighbor filtering so pixels stay crisp. For 3D, keep texel density (pixels per meter) similar across objects so nothing looks blurry next to something sharp.

## Godot 4 art pipeline tips
Import 3D models as glTF 2.0 (.glb). Use the Godot import dock to set texture compression (VRAM compressed for 3D, lossless for UI and pixel art) and turn off filtering for pixel art. Use Control nodes and Containers for UI so it scales with screen size; set anchors so HUD pieces stick to their corners. Theme resources keep fonts, colors and button styles consistent across every screen.

## Icons and UI style for a military game
A restrained palette (olive, khaki, gunmetal, off-white) with one alert color (amber or red) reads as military and keeps alerts loud. Stencil or condensed sans-serif fonts fit the theme; keep body text a plain, readable sans-serif. Icons should be simple silhouettes on a consistent grid, readable at 32 pixels.

## Performance basics for art
Fewer draw calls is faster: batch, atlas, and reuse materials. Use LOD (level of detail): simpler models far away. Bake lighting where things don't move. Keep UI textures small; a HUD that redraws every frame should be cheap.
