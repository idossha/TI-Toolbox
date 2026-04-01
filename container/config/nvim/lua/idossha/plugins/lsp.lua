return {
  -- LSP configuration for Python (pylsp) — provides autocompletion,
  -- signature help, hover docs, and go-to-definition for tit + simnibs.
  {
    "neovim/nvim-lspconfig",
    dependencies = {
      "hrsh7th/nvim-cmp",
      "hrsh7th/cmp-nvim-lsp",
      "hrsh7th/cmp-buffer",
      "hrsh7th/cmp-path",
      "L3MON4D3/LuaSnip",
      "saadparwaiz1/cmp_luasnip",
    },
    config = function()
      local lspconfig = require("lspconfig")
      local cmp = require("cmp")
      local cmp_nvim_lsp = require("cmp_nvim_lsp")
      local luasnip = require("luasnip")

      -- Broadened capabilities for LSP (completion, snippets)
      local capabilities = cmp_nvim_lsp.default_capabilities()

      -- Resolve the SimNIBS Python interpreter so pylsp uses the right env
      local simnibs_python = vim.fn.exepath("simnibs_python")
      if simnibs_python == "" then
        simnibs_python = nil
      end

      lspconfig.pylsp.setup({
        capabilities = capabilities,
        cmd = { simnibs_python or "python3", "-m", "pylsp" },
        settings = {
          pylsp = {
            plugins = {
              jedi_completion = { enabled = true, include_params = true },
              jedi_hover = { enabled = true },
              jedi_signature_help = { enabled = true },
              jedi_definition = { enabled = true, follow_imports = true },
              jedi = {
                extra_paths = { "/ti-toolbox" },
              },
              -- Disable noisy linters for scripting environment
              pycodestyle = { enabled = false },
              pyflakes = { enabled = false },
              mccabe = { enabled = false },
              pydocstyle = { enabled = false },
            },
          },
        },
      })

      -- LSP keybindings (activated when an LSP attaches to a buffer)
      vim.api.nvim_create_autocmd("LspAttach", {
        group = vim.api.nvim_create_augroup("UserLspConfig", {}),
        callback = function(ev)
          local opts = { buffer = ev.buf }
          vim.keymap.set("n", "gd", vim.lsp.buf.definition, vim.tbl_extend("force", opts, { desc = "Go to definition" }))
          vim.keymap.set("n", "gD", vim.lsp.buf.declaration, vim.tbl_extend("force", opts, { desc = "Go to declaration" }))
          vim.keymap.set("n", "gr", vim.lsp.buf.references, vim.tbl_extend("force", opts, { desc = "List references" }))
          vim.keymap.set("n", "K", vim.lsp.buf.hover, vim.tbl_extend("force", opts, { desc = "Hover documentation" }))
          vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename, vim.tbl_extend("force", opts, { desc = "Rename symbol" }))
          vim.keymap.set("i", "<C-k>", vim.lsp.buf.signature_help, vim.tbl_extend("force", opts, { desc = "Signature help" }))
        end,
      })

      -- Autocompletion setup
      cmp.setup({
        snippet = {
          expand = function(args)
            luasnip.lsp_expand(args.body)
          end,
        },
        mapping = cmp.mapping.preset.insert({
          ["<C-b>"] = cmp.mapping.scroll_docs(-4),
          ["<C-f>"] = cmp.mapping.scroll_docs(4),
          ["<C-Space>"] = cmp.mapping.complete(),
          ["<C-e>"] = cmp.mapping.abort(),
          ["<CR>"] = cmp.mapping.confirm({ select = true }),
          ["<Tab>"] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.select_next_item()
            elseif luasnip.expand_or_jumpable() then
              luasnip.expand_or_jump()
            else
              fallback()
            end
          end, { "i", "s" }),
          ["<S-Tab>"] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.select_prev_item()
            elseif luasnip.jumpable(-1) then
              luasnip.jump(-1)
            else
              fallback()
            end
          end, { "i", "s" }),
        }),
        sources = cmp.config.sources({
          { name = "nvim_lsp" },
          { name = "luasnip" },
        }, {
          { name = "buffer" },
          { name = "path" },
        }),
      })
    end,
  },
}
