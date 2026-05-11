export const queryKeys = {
  meetings: (params: { workspace_id: string }) =>
    ['meetings', params.workspace_id] as const,
  meeting: (id: string) => ['meeting', id] as const,
  transcript: (id: string) => ['transcript', id] as const,
};
