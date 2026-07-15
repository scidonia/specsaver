{
  description = "specsaver — specification-driven verification";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix.url = "github:numtide/treefmt-nix";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uvpart = {
      url = "github:matko/uvpart";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.pyproject-build-systems.follows = "pyproject-build-systems";
    };

    uvpart-fixups = {
      url = "github:matko/uvpart-fixups";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs @ {flake-parts, ...}:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin"];
      imports = [
        inputs.treefmt-nix.flakeModule
        inputs.uvpart.flakeModule
        inputs.uvpart-fixups.flakeModule
      ];
      perSystem = {
        pkgs,
        config,
        ...
      }: {
        treefmt = {
          projectRootFile = "pyproject.toml";
          programs = {
            nixfmt.enable = true;
            black.enable = true;
            mdformat.enable = true;
            taplo.enable = true;
            ruff-check.enable = true;
            ruff-format.enable = true;
          };
          settings.formatter = {
            ruff-check.excludes = [".envrc" ".python-version"];
            ruff-format.excludes = [".envrc" ".python-version"];
          };
        };

        uvpart = {
          workspaceRoot = ./.;
          python = pkgs.python312;
          extraPackages = [pkgs.python3 pkgs.ruff];
        };
      };
    };
}
