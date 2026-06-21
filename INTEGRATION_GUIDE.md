# CodeMemory Integration Guide

Welcome! This guide explains in simple, plain language how to connect **CodeMemory** with your favorite AI coding agents (like **Antigravity**, **Cursor**, **Cline/Roo Code**, **Codex**, and **Claude Desktop**). 

By connecting CodeMemory, your AI agent gains instant access to deep codebase intelligence, semantic search, knowledge graphs, and memory—without needing to read every file in your repository from scratch.

---

## Step 1: Initialize and Scan Your Repository

Before connecting your agent, CodeMemory needs to scan and index your repository.

1. Open your terminal in your repository's root directory.
2. Run the initialization command:
   ```bash
   codememory init
   ```
3. Run a full repository scan to build your index, knowledge graph, and embeddings:
   ```bash
   codememory scan
   ```
   *(This creates a local database in your user folder under `~/.codememory/`, so your repository stays completely clean!)*

---

## Step 2: Connecting to Cursor (AI Code Editor)

Cursor supports the Model Context Protocol (MCP) natively, allowing you to add CodeMemory in just a few clicks.

### Option A: Via Cursor Settings UI (Recommended)
1. Open Cursor and go to **Settings** (gear icon in the top right or `Ctrl+,` / `Cmd+,`).
2. Navigate to **Features** -> **MCP**.
3. Click **+ Add New MCP Server**.
4. Fill in the fields:
   - **Name**: `codememory`
   - **Type**: `command`
   - **Command**: Enter the absolute path to your Python executable or virtual environment's `codememory` runner:
     - **Windows (Virtual Env)**: `C:\path\to\your\venv\Scripts\codememory.exe`
     - **macOS/Linux (Virtual Env)**: `/path/to/your/venv/bin/codememory`
     - **Global Installation**: `codememory`
   - **Arguments**: `serve /path/to/your/repository --stdio`
     *(Replace `/path/to/your/repository` with the absolute path of the repository you want the agent to see.)*
5. Click **Save**. The status should change to a green dot (Connected).

### Option B: Via Workspace Config
Create a file named `.cursor/mcp.json` in your repository root and paste the following configuration:
```json
{
  "mcpServers": {
    "codememory": {
      "command": "codememory",
      "args": [
        "serve",
        "/absolute/path/to/your/repository",
        "--stdio"
      ]
    }
  }
}
```

---

## Step 3: Connecting to Antigravity (Gemini Agent)

Antigravity uses custom MCP configurations to load tools at startup.

1. Copy the absolute path of your repository.
2. Ensure `codememory` is accessible in your shell environment.
3. Configure the `mcp_servers` configuration in your global settings or active workspace configurations:
   ```json
   "mcpServers": {
     "codememory": {
       "command": "codememory",
       "args": [
         "serve",
         "/absolute/path/to/your/repository",
         "--stdio"
       ]
     }
   }
   ```
4. Start your Antigravity agent session. It will automatically load CodeMemory's 21+ search and intelligence tools!

---

## Step 4: Connecting to Cline / Roo Code / Codex (VS Code Extensions)

Cline and Roo Code (formerly Previti/Codex) are popular AI agent extensions for VS Code.

1. Open VS Code.
2. In the extension pane on the left, click on the **Cline** or **Roo Code** icon.
3. Click the **Settings** gear icon inside the extension panel.
4. Select **MCP Servers** or edit the settings file.
5. Add the following server definition to your active custom servers list:
   - **Server ID**: `codememory`
   - **Command**: `codememory` *(or the absolute path to your `codememory` script)*
   - **Arguments**: `["serve", "/absolute/path/to/your/repository", "--stdio"]`
6. Click **Save**. The extension will automatically spawn the process and verify connection.

---

## Step 5: Connecting to Claude Desktop (Standalone App)

To make CodeMemory available to the standalone Claude Desktop application:

1. Open your Claude Desktop configuration file:
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Add CodeMemory to the `mcpServers` object:
   ```json
   {
     "mcpServers": {
       "codememory": {
         "command": "codememory",
         "args": [
           "serve",
           "/absolute/path/to/your/repository",
           "--stdio"
         ]
       }
     }
   }
   ```
3. Restart the Claude Desktop app. You should see a small socket/plug icon indicating that MCP tools are active.

---

## How to Verify the Connection

Once connected, you can ask your AI agent to test the connection. Try asking:
* *"What is the Repository Health Score of this project?"*
* *"Show me the Architecture Decision Records (ADRs) for this repository."*
* *"Can you search semantically for the database schema class?"*

If connected properly, the agent will execute the underlying CodeMemory MCP tool and display the results instantly!
