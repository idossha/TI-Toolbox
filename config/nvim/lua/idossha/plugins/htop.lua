return {
  {
    "idossha/htop.nvim",
    config = function()
      vim.keymap.set("n", "<leader>H", require("htop").open, { desc = "Open floating htop" })
    end,
  },
}

