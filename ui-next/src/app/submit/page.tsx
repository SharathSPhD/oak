"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function SubmitPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [autoStart, setAutoStart] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<"form" | "creating" | "uploading" | "starting" | "done">("form");

  const createMutation = useMutation({
    mutationFn: async () => {
      setStep("creating");
      const problem = await api.problems.create({ title, description });

      if (file) {
        setStep("uploading");
        await api.problems.upload(problem.id, file);
      }

      if (autoStart) {
        setStep("starting");
        await api.problems.start(problem.id);
      }

      setStep("done");
      return problem;
    },
    onSuccess: (problem) => {
      setTimeout(() => router.push(`/problems/${problem.id}`), 800);
    },
  });

  const isSubmitting = step !== "form" && step !== "done";

  return (
    <div className="max-w-2xl">
      <div className="page-header">
        <h1 className="page-title">Submit a Problem</h1>
        <p className="page-subtitle">
          Define an analytical problem for the agent pipeline to solve.
        </p>
      </div>

      <Card>
        <CardContent className="py-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
            className="space-y-6"
          >
            <div>
              <label htmlFor="title" className="block text-sm font-medium text-slate-700 mb-1.5">
                Problem Title
              </label>
              <input
                id="title"
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Sales Forecast Q4 2025"
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-oak-500 focus:ring-2 focus:ring-oak-500/20 focus:outline-none transition-colors"
              />
            </div>

            <div>
              <label htmlFor="desc" className="block text-sm font-medium text-slate-700 mb-1.5">
                Description
              </label>
              <textarea
                id="desc"
                required
                rows={5}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the problem, expected outputs, and any constraints..."
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-oak-500 focus:ring-2 focus:ring-oak-500/20 focus:outline-none transition-colors resize-y"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Data File (optional)
              </label>
              <div
                onClick={() => fileRef.current?.click()}
                className="flex cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-8 transition-colors hover:border-oak-400 hover:bg-oak-50/30"
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv,.json,.xlsx,.parquet"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                <div className="text-center">
                  <svg className="mx-auto h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}><path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" /></svg>
                  {file ? (
                    <p className="mt-2 text-sm font-medium text-oak-700">{file.name} ({(file.size / 1024).toFixed(1)} KB)</p>
                  ) : (
                    <>
                      <p className="mt-2 text-sm text-slate-600">Click to upload CSV, JSON, XLSX, or Parquet</p>
                      <p className="text-xs text-slate-400">or drag and drop</p>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="autostart"
                checked={autoStart}
                onChange={(e) => setAutoStart(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-oak-600 focus:ring-oak-500"
              />
              <label htmlFor="autostart" className="text-sm text-slate-700">
                Start agent pipeline automatically after submission
              </label>
            </div>

            {createMutation.error && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                {(createMutation.error as Error).message}
              </div>
            )}

            {step !== "form" && step !== "done" && (
              <div className="rounded-lg bg-oak-50 border border-oak-200 px-4 py-3">
                <div className="flex items-center gap-2">
                  <svg className="h-4 w-4 animate-spin text-oak-600" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-sm font-medium text-oak-700">
                    {step === "creating" && "Creating problem..."}
                    {step === "uploading" && "Uploading file..."}
                    {step === "starting" && "Starting pipeline..."}
                  </span>
                </div>
              </div>
            )}

            {step === "done" && (
              <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700">
                Problem created successfully. Redirecting...
              </div>
            )}

            <Button
              type="submit"
              size="lg"
              className="w-full"
              loading={isSubmitting}
              disabled={!title || !description || isSubmitting}
            >
              Submit Problem
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
