type Props = {
  label: string;
  value: string | number;
};

export function StatChip({ label, value }: Props) {
  return (
    <div className="rounded border border-gray-200 bg-gray-50 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}
