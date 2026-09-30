# Runtime license notices

`unreal/` retains the core third-party license text files supplied with the
installed Unreal Engine 5.8.3 under `Engine/Source/ThirdParty/Licenses`.
The folder includes notices for optional engine components as well as the
packaged runtime's dependencies. Marketplace plugin subdirectories are not
included. `tools/build_linux.sh package` copies these notices into the Linux
client's `Licenses/unreal/` folder, alongside the engine-generated root
`NOTICES.txt`.

The default HUD font is engine-bundled Roboto. Its supplied `Roboto.tps`
identifies `ROBOTO_License.txt`, which retains the Google font copyright and
Apache 2.0 terms. The manifest records this separately from Epic's original
showcase support geometry.

Character geometry, textures, costume, equipped props, rig and motion curves
are original project work. Authoring tools such as Blender, eSpeak NG and
FFmpeg are dependencies; their executables are supplied by the documented
host environment and are not packaged in this delivery.
