-- surrounding delimiters pairs wioth ease. Written in lua.
-- see nvim/idossa/test/surround.py for examples
return {
  "kylechui/nvim-surround",
  event = { "BufReadPre", "BufNewFile" },
  version = "*", -- Use for stability; omit to use `main` branch for the latest features
  config = true,
}
