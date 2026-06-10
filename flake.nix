{
  description = "Development shell for donnietts";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          lib = pkgs.lib;

          python = pkgs.python312;

          nativeLibs = with pkgs; [
            stdenv.cc.cc
            zlib
            openssl
            libffi
            portaudio
            libsndfile
          ];
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python
              uv
              pkg-config
              portaudio
              libsndfile
              ffmpeg
            ];

            env = {
              UV_PYTHON = "${python}/bin/python3.12";
              UV_PYTHON_DOWNLOADS = "never";
              LD_LIBRARY_PATH = lib.makeLibraryPath nativeLibs;
              DYLD_LIBRARY_PATH = lib.makeLibraryPath nativeLibs;
            };

            shellHook = ''
              echo "Nix shell ready: Python $(python --version), uv $(uv --version)"
              echo "First run: uv sync --frozen"
              echo "Then run:  uv run python speak.py"
            '';
          };
        });
    };
}
