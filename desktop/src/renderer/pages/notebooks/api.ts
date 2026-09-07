/** `/api/notebooks` and `/api/kernels`, page-local as every page's calls are. */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { Notebook } from "./notebook";

export type NotebookEntry = components["schemas"]["NotebookEntry"];
export type NotebookList = components["schemas"]["NotebookList"];
export type Kernel = components["schemas"]["Kernel"];
export type KernelList = components["schemas"]["KernelList"];

export async function listNotebooks(): Promise<NotebookList> {
  return unwrap(await api.GET("/api/notebooks"), "/api/notebooks");
}

export async function readNotebook(name: string): Promise<{ name: string; content: Notebook }> {
  const result = unwrap(
    await api.GET("/api/notebooks/{name}", { params: { path: { name } } }),
    "/api/notebooks/{name}",
  );
  return { name: result.name, content: result.content as unknown as Notebook };
}

export async function createNotebook(
  name: string,
  content?: Notebook,
): Promise<{ name: string; content: Notebook }> {
  const result = unwrap(
    await api.POST("/api/notebooks", {
      body: { name, ...(content ? { content: content as unknown as Record<string, never> } : {}) },
    }),
    "/api/notebooks",
  );
  return { name: result.name, content: result.content as unknown as Notebook };
}

export async function saveNotebook(name: string, content: Notebook): Promise<NotebookEntry> {
  return unwrap(
    await api.PUT("/api/notebooks/{name}", {
      params: { path: { name } },
      body: { content: content as unknown as Record<string, never> },
    }),
    "/api/notebooks/{name}",
  );
}

export async function deleteNotebook(name: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/notebooks/{name}", { params: { path: { name } } }),
    "/api/notebooks/{name}",
  );
}

export async function listKernels(): Promise<KernelList> {
  return unwrap(await api.GET("/api/kernels"), "/api/kernels");
}

export async function startKernel(): Promise<Kernel> {
  return unwrap(await api.POST("/api/kernels", { body: {} }), "/api/kernels");
}

export async function interruptKernel(kernelId: string): Promise<void> {
  unwrap(
    await api.POST("/api/kernels/{kernel_id}/interrupt", {
      params: { path: { kernel_id: kernelId } },
    }),
    "/api/kernels/{kernel_id}/interrupt",
  );
}

export async function restartKernel(kernelId: string): Promise<Kernel> {
  return unwrap(
    await api.POST("/api/kernels/{kernel_id}/restart", {
      params: { path: { kernel_id: kernelId } },
    }),
    "/api/kernels/{kernel_id}/restart",
  );
}

export async function stopKernel(kernelId: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/kernels/{kernel_id}", { params: { path: { kernel_id: kernelId } } }),
    "/api/kernels/{kernel_id}",
  );
}
