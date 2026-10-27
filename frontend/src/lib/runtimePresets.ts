import type { RuntimeWrite } from "../api/types";

export interface RuntimePreset {
  label: string;
  runtime: RuntimeWrite;
}

export const RUNTIME_PRESETS: RuntimePreset[] = [
  {
    label: "llama.cpp server",
    runtime: {
      name: "llama.cpp",
      description: "llama-server with native tool calling. Select a .gguf file in the deployment.",
      kind: "managed",
      command_template: "llama-server -m {model_path} --host {host} --port {port} --jinja -c 16384",
      base_url: null,
      health_path: "/health",
      startup_timeout_seconds: 600,
    },
  },
  {
    label: "vLLM",
    runtime: {
      name: "vLLM",
      description: "vLLM OpenAI-compatible server. Linux and WSL only.",
      kind: "managed",
      command_template:
        "vllm serve {model_dir} --host {host} --port {port} --served-model-name {served_model_name} " +
        "--enable-auto-tool-choice --tool-call-parser hermes",
      base_url: null,
      health_path: "/health",
      startup_timeout_seconds: 1200,
    },
  },
  {
    label: "SGLang",
    runtime: {
      name: "SGLang",
      description: "SGLang server. Linux and WSL only.",
      kind: "managed",
      command_template:
        "python -m sglang.launch_server --model-path {model_dir} --host {host} --port {port} " +
        "--served-model-name {served_model_name} --tool-call-parser qwen25",
      base_url: null,
      health_path: "/health",
      startup_timeout_seconds: 1200,
    },
  },
  {
    label: "Strata (external)",
    runtime: {
      name: "Strata",
      description: "A running Strata instance. Set the served model name to the Strata model ID.",
      kind: "external",
      command_template: null,
      base_url: "http://127.0.0.1:47831",
      health_path: "/v1/models",
      startup_timeout_seconds: 30,
    },
  },
  {
    label: "Ollama (external)",
    runtime: {
      name: "Ollama",
      description: "A running Ollama service. Set the served model name to the Ollama model tag.",
      kind: "external",
      command_template: null,
      base_url: "http://127.0.0.1:11434",
      health_path: "/v1/models",
      startup_timeout_seconds: 30,
    },
  },
  {
    label: "LM Studio (external)",
    runtime: {
      name: "LM Studio",
      description: "The LM Studio local server. Set the served model name to the loaded model.",
      kind: "external",
      command_template: null,
      base_url: "http://127.0.0.1:1234",
      health_path: "/v1/models",
      startup_timeout_seconds: 30,
    },
  },
];

export const EMPTY_RUNTIME: RuntimeWrite = {
  name: "",
  description: "",
  kind: "managed",
  command_template: "",
  base_url: null,
  health_path: "/v1/models",
  startup_timeout_seconds: 600,
};
