-- wish there was a way to select/paste after closing the telescope window
-- maybe with handlers?
return {
      "AckslD/nvim-neoclip.lua",
      dependencies = {
        -- {'kkharji/sqlite.lua', module = 'sqlite'},
        -- you'll need at least one of these
        -- {'nvim-telescope/telescope.nvim'},
        {'ibhagwan/fzf-lua'},
      },
      config = function()
        require('neoclip').setup({
          default_register = '"',
          default_register_macros = 'q',
          on_select = {
            move_to_front = false,
            close_telescope = true,
          },
          on_paste = {
            set_reg = true,  -- Make sure this is true
            move_to_front = false,
            close_telescope = true,
  },
    })
  end,
}
