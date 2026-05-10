import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { importConversation, type ImportInput, type Visibility } from '../api/client';
import { MAX_UPLOAD_BYTES } from '../lib/constants';
import axios from 'axios';

type Mode = 'upload' | 'paste';

const ACCEPT = {
  'audio/*': [],
  'text/vtt': ['.vtt'],
  'application/x-subrip': ['.srt'],
  'text/plain': ['.txt'],
};

function classifyFile(file: File): 'voice_file' | 'transcript_file' {
  return file.type.startsWith('audio/') ? 'voice_file' : 'transcript_file';
}

function friendlyImportError(detail: unknown): string {
  if (typeof detail === 'object' && detail !== null && 'code' in detail) {
    const code = (detail as { code?: string }).code;
    if (code === 'no_input') return 'Please add a transcript, audio file, or pasted text.';
    if (code === 'multiple_inputs') return 'Provide exactly one of file or pasted text.';
    if (code === 'invalid_format') return 'That file format is not supported.';
  }
  return 'Import failed. Please try again.';
}

export default function ImportPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>('upload');
  const [title, setTitle] = useState('');
  const [titleError, setTitleError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [pasted, setPasted] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('private');
  const [labelsRaw, setLabelsRaw] = useState('');

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPT,
    multiple: false,
    onDrop: (accepted) => {
      const f = accepted[0];
      if (!f) return;
      if (f.size > MAX_UPLOAD_BYTES) {
        setFileError('File exceeds 100 MB limit.');
        setFile(null);
        return;
      }
      setFileError(null);
      setFile(f);
    },
  });

  const mutation = useMutation({
    mutationFn: (input: ImportInput) => importConversation(input),
    onSuccess: (data) => {
      localStorage.setItem('meeting-title:' + data.meeting_id, title);
      navigate(`/meetings/${data.meeting_id}/processing`);
    },
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      setTitleError('Title is required.');
      return;
    }
    setTitleError(null);

    const labels = labelsRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    const input: ImportInput = { title: trimmed, visibility, labels };
    if (mode === 'paste') {
      input.pasted_transcript = pasted;
    } else if (file) {
      const kind = classifyFile(file);
      input[kind] = file;
    }
    mutation.mutate(input);
  }

  const submitErrorMessage =
    mutation.isError && axios.isAxiosError(mutation.error)
      ? friendlyImportError(mutation.error.response?.data)
      : mutation.isError
        ? 'Import failed. Please try again.'
        : null;

  return (
    <form onSubmit={onSubmit} className="mx-auto max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">Import a conversation</h1>

      <div className="flex gap-2" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'upload'}
          className={`rounded border px-3 py-1 ${mode === 'upload' ? 'bg-gray-900 text-white' : 'bg-white'}`}
          onClick={() => setMode('upload')}
        >
          Upload file
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'paste'}
          className={`rounded border px-3 py-1 ${mode === 'paste' ? 'bg-gray-900 text-white' : 'bg-white'}`}
          onClick={() => setMode('paste')}
        >
          Paste transcript
        </button>
      </div>

      {mode === 'upload' ? (
        <div>
          <div
            {...getRootProps()}
            className={`cursor-pointer rounded border-2 border-dashed p-6 text-center ${
              isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
            }`}
          >
            <input {...getInputProps()} aria-label="Upload file" />
            {file ? (
              <p>
                {file.name} ({Math.round(file.size / 1024)} KB)
              </p>
            ) : (
              <p>Drop an audio or transcript file, or click to choose.</p>
            )}
          </div>
          {fileError && <p className="mt-1 text-sm text-red-600">{fileError}</p>}
        </div>
      ) : (
        <div>
          <label className="block text-sm font-medium">Pasted transcript</label>
          <textarea
            className="mt-1 h-40 w-full rounded border border-gray-300 p-2"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            aria-label="Pasted transcript"
          />
        </div>
      )}

      <div>
        <label className="block text-sm font-medium" htmlFor="title">
          Title
        </label>
        <input
          id="title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="mt-1 w-full rounded border border-gray-300 p-2"
        />
        {titleError && <p className="mt-1 text-sm text-red-600">{titleError}</p>}
      </div>

      <div>
        <label className="block text-sm font-medium" htmlFor="visibility">
          Visibility
        </label>
        <select
          id="visibility"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as Visibility)}
          className="mt-1 w-full rounded border border-gray-300 p-2"
        >
          <option value="private">private</option>
          <option value="workspace">workspace</option>
          <option value="shared">shared</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium" htmlFor="labels">
          Labels (comma-separated)
        </label>
        <input
          id="labels"
          type="text"
          value={labelsRaw}
          onChange={(e) => setLabelsRaw(e.target.value)}
          className="mt-1 w-full rounded border border-gray-300 p-2"
        />
      </div>

      <button
        type="submit"
        disabled={mutation.isPending}
        className="rounded bg-gray-900 px-4 py-2 text-white disabled:opacity-50"
      >
        {mutation.isPending ? 'Submitting…' : 'Submit'}
      </button>

      {submitErrorMessage && <p className="text-sm text-red-600">{submitErrorMessage}</p>}
    </form>
  );
}
