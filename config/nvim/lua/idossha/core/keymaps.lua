-- set leader key to space
vim.g.mapleader = " "

local keymap = vim.keymap -- for conciseness


----------------------- Remaining free keys ---------------



----------------------- General Keymaps -------------------

-- use jk to exit insert mode
keymap.set("i", "jk", "<ESC>", { desc = "Exit insert mode with jk" })

-- clear search highlights
keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })


-- harpoon
keymap.set("n", "<leader>hr", "<cmd>lua require('harpoon.mark').rm_file()<cr>", { desc = "Remove harpoon mark" })
keymap.set("n", "<leader>h1", "<cmd>lua require('harpoon.ui').nav_file(1)<cr>", { desc = "Go to harpoon mark 1" })
keymap.set("n", "<leader>h2", "<cmd>lua require('harpoon.ui').nav_file(2)<cr>", { desc = "Go to harpoon mark 2" })
keymap.set("n", "<leader>h3", "<cmd>lua require('harpoon.ui').nav_file(3)<cr>", { desc = "Go to harpoon mark 3" })
keymap.set("n", "<leader>h4", "<cmd>lua require('harpoon.ui').nav_file(4)<cr>", { desc = "Go to harpoon mark 4" })
keymap.set("n","<leader>hm", "<cmd>lua require('harpoon.mark').add_file()<cr>",{ desc = "Mark file with harpoon" })
keymap.set("n", "<leader>hn", "<cmd>lua require('harpoon.ui').nav_next()<cr>", { desc = "Go to next harpoon mark" })
keymap.set("n","<leader>hp", "<cmd>lua require('harpoon.ui').nav_prev()<cr>",{ desc = "Go to previous harpoon mark" })
keymap.set("n","<leader>hh", "<cmd>lua require('harpoon.ui').toggle_quick_menu()<cr>",{ desc = "Harpoon quick menu" })

-- nvim-tree
keymap.set("n", "<leader>ee", "<cmd>NvimTreeToggle<CR>", { desc = "Toggle file explorer" }) -- toggle file explorer
keymap.set("n", "<leader>er", "<cmd>NvimTreeRefresh<CR>", { desc = "Refresh file explorer" }) -- refresh file explorer

-- telescope.lua:
keymap.set("n", "<leader>ff", "<cmd>Telescope find_files<cr>", { desc = "Fuzzy find files in cwd" })
keymap.set("n", "<leader>fr", "<cmd>Telescope oldfiles<cr>", { desc = "Fuzzy find recent files" })
keymap.set("n", "<leader>fs", "<cmd>Telescope live_grep<cr>", { desc = "Find string in cwd" })
keymap.set("n", "<leader>fc", "<cmd>Telescope grep_string<cr>", { desc = "Find string under cursor in cwd" })

----------------------------------------------------------------------
--- Snacks are placed within the plugin file for simplicity
----------------------------------------------------------------------

-- conform.lua:
-- 1) Toggle Conform formatting
keymap.set("n", "<leader>Ft", function()
  -- Import your plugin module
  require("idossha.plugins.conform").toggle_formatting()
end, { desc = "Toggle Conform auto-formatting" })

-- 2) Manually format
--    - Works in Normal mode (format buffer)
--    - Works in Visual mode (format selection)
keymap.set({ "n", "v" }, "<leader>Fp", function()
  require("conform").format({
    async = false,
    timeout_ms = 3000,
  })
end, { desc = "Format with Conform" })


-- In your keymaps.lua or init.lua
vim.keymap.set('n', '<leader>cy', function()
  require('telescope').extensions.neoclip.default()
end, { desc = 'Yank history' })

-- For macros history (if enabled)
vim.keymap.set('n', '<leader>cm', function()
  require('telescope').extensions.macroscope.default()
end, { desc = 'Macro history' })
