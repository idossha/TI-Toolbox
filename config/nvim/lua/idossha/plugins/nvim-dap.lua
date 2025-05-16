
--[[
Create virtual environment for debugpy if you haven't already
python -m venv ~/.virtualenvs/debugpy
~/.virtualenvs/debugpy/bin/pip install debugpy
Press <F5> to start debugging
Use <F10> to step over, <F11> to step into functions
Press <leader>du to toggle the debug UI if it's not already open
there is a test scipt under: idossha/test/
--]]
return {
  "mfussenegger/nvim-dap",
  dependencies = {
    "rcarriga/nvim-dap-ui",
    "nvim-neotest/nvim-nio", -- Good, this is required for newer versions of dap-ui
    "mfussenegger/nvim-dap-python",
    "theHamsta/nvim-dap-virtual-text",
  },
  config = function()
    -- Basic DAP configuration
    local dap = require("dap")
    local dapui = require("dapui")
    local dap_python = require("dap-python")
    local dap_virtual_text = require("nvim-dap-virtual-text")
    
    -- Python DAP setup
    -- Update this path to point to your Python environment with debugpy installed
    dap_python.setup("~/.virtualenvs/debugpy/bin/python")
    dap_python.test_runner = "pytest"
    
    -- DAP UI setup
    dapui.setup()
    
    -- Virtual text setup
    dap_virtual_text.setup({
      enabled = true,
      enabled_commands = true,
      highlight_changed_variables = true,
      highlight_new_as_changed = false,
      show_stop_reason = true,
      commented = false,
    })
    
    -- Automatically open/close DAP UI
    dap.listeners.after.event_initialized["dapui_config"] = function()
      dapui.open()
    end
    dap.listeners.before.event_terminated["dapui_config"] = function()
      dapui.close()
    end
    dap.listeners.before.event_exited["dapui_config"] = function()
      dapui.close()
    end
  end,
  keys = {
    -- Add keybindings here
    { "<F5>", function() require("dap").continue() end, desc = "Debug: Continue" },
    { "<F10>", function() require("dap").step_over() end, desc = "Debug: Step Over" },
    { "<F11>", function() require("dap").step_into() end, desc = "Debug: Step Into" },
    { "<F12>", function() require("dap").step_out() end, desc = "Debug: Step Out" },
    { "<leader>db", function() require("dap").toggle_breakpoint() end, desc = "Debug: Toggle Breakpoint" },
    { "<leader>dB", function() 
        require("dap").set_breakpoint(vim.fn.input("Breakpoint condition: ")) 
      end, desc = "Debug: Conditional Breakpoint" },
    { "<leader>dl", function() 
        require("dap").set_breakpoint(nil, nil, vim.fn.input("Log point message: ")) 
      end, desc = "Debug: Log Point" },
    { "<leader>dr", function() require("dap").repl.open() end, desc = "Debug: Open REPL" },
    { "<leader>du", function() require("dapui").toggle() end, desc = "Debug: Toggle UI" },
  },
}
