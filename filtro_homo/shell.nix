{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python312
    pkgs.python312Packages.pymongo
    pkgs.python312Packages.requests
    pkgs.pig
    pkgs.curl
  ];

  shellHook = ''
    python main.py
  '';
}

