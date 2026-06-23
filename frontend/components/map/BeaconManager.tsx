"use client";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  listBeacons, createBeacon, updateBeacon, deleteBeacon,
  type BeaconRecord, type PersonType,
} from "@/services/beaconService";
import { toast } from "@/store/toastStore";

const PERSON_TYPES: PersonType[] = ["guard", "worker", "forklift"];

interface Props {
  onClose?: () => void;
}

interface FormState {
  uuid: string;
  major: string;
  minor: string;
  person_id: string;
  person_type: PersonType;
  label: string;
}

const EMPTY_FORM: FormState = {
  uuid: "", major: "", minor: "",
  person_id: "", person_type: "guard", label: "",
};

export default function BeaconManager({ onClose }: Props) {
  const [beacons, setBeacons] = useState<BeaconRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null); // null = create mode
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    listBeacons()
      .then(setBeacons)
      .catch(() => toast.error("Failed to load beacons"))
      .finally(() => setLoading(false));
  }, []);

  const openCreate = () => {
    setEditingId(null); setForm(EMPTY_FORM); setFormError(""); setModalOpen(true);
  };

  const openEdit = (b: BeaconRecord) => {
    setEditingId(b.id);
    setForm({
      uuid: b.uuid, major: b.major, minor: b.minor,
      person_id: b.person_id, person_type: b.person_type, label: b.label,
    });
    setFormError(""); setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false); setEditingId(null); setForm(EMPTY_FORM); setFormError("");
  };

  const handleSave = async () => {
    if (!editingId && (!form.uuid.trim() || !form.major.trim() || !form.minor.trim())) {
      setFormError("UUID, major, and minor are all required"); return;
    }
    if (!form.person_id.trim()) { setFormError("Person ID is required"); return; }
    if (!form.label.trim())     { setFormError("Label is required"); return; }
    setFormError("");
    setSaving(true);
    try {
      if (editingId) {
        const updated = await updateBeacon(editingId, {
          person_id: form.person_id.trim(),
          person_type: form.person_type,
          label: form.label.trim(),
        });
        setBeacons((prev) => prev.map((b) => (b.id === editingId ? updated : b)));
        toast.success(`Beacon "${updated.label}" updated`);
      } else {
        const created = await createBeacon({
          uuid: form.uuid.trim(),
          major: form.major.trim(),
          minor: form.minor.trim(),
          person_id: form.person_id.trim(),
          person_type: form.person_type,
          label: form.label.trim(),
        });
        setBeacons((prev) => [...prev, created]);
        toast.success(`Beacon "${created.label}" registered`);
      }
      closeModal();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("409") || msg.toLowerCase().includes("already exists")) {
        setFormError("A beacon with this UUID / major / minor already exists.");
      } else {
        toast.error(editingId ? "Failed to update beacon" : "Failed to register beacon");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await deleteBeacon(id);
      setBeacons((prev) => prev.filter((b) => b.id !== id));
      toast.success("Beacon removed");
    } catch {
      toast.error("Failed to remove beacon");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase mr-1">Beacons</span>
        <button
          onClick={openCreate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-s-accent text-s-base transition-colors hover:opacity-90"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Register Beacon
        </button>
        {onClose && (
          <button onClick={onClose} className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs font-mono text-s-muted hover:text-s-danger transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            Close
          </button>
        )}
      </div>

      {/* Beacon list */}
      {loading ? (
        <p className="font-mono text-[10px] text-s-muted text-center py-4 tracking-widest">Loading beacons…</p>
      ) : beacons.length > 0 ? (
        <div className="bento-card p-0 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-s-border">
                {["Person", "Type", "iBeacon (UUID · Major · Minor)", ""].map((h) => (
                  <th key={h} className="font-mono text-[10px] text-s-muted tracking-widest uppercase text-left px-4 py-2.5">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {beacons.map((b) => (
                <tr key={b.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex flex-col leading-tight">
                      <span className="text-s-text font-medium">{b.label}</span>
                      <span className="font-mono text-[10px] text-s-muted">{b.person_id}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-s-elevated border border-s-border text-s-muted capitalize">{b.person_type}</span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted break-all">
                    <span className="text-s-text">{b.uuid}</span> · {b.major} · {b.minor}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <button onClick={() => openEdit(b)} className="text-s-muted hover:text-s-accent transition-colors" title="Edit">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      </button>
                      <button onClick={() => handleDelete(b.id)} disabled={deletingId === b.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40" title="Delete">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="font-mono text-[10px] text-s-muted text-center py-4 tracking-widest">
          No beacons registered. Register one above.
        </p>
      )}

      {/* Create / Edit modal */}
      {modalOpen && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={closeModal}>
          <div className="w-full max-w-sm rounded-xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-s-border">
              <h3 className="font-mono text-xs text-s-muted tracking-widest uppercase">
                {editingId ? "Edit Beacon" : "Register Beacon"}
              </h3>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  iBeacon UUID <span className="text-s-danger">*</span>
                </label>
                <input
                  autoFocus={!editingId}
                  type="text"
                  placeholder="c001405c0e9f43b8af4aea309ba7e130"
                  value={form.uuid}
                  onChange={(e) => setForm((p) => ({ ...p, uuid: e.target.value }))}
                  disabled={!!editingId}
                  className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors disabled:opacity-50"
                />
              </div>
              <div className="flex gap-3">
                <div className="space-y-1 flex-1">
                  <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                    Major <span className="text-s-danger">*</span>
                  </label>
                  <input
                    type="text" placeholder="0001"
                    value={form.major}
                    onChange={(e) => setForm((p) => ({ ...p, major: e.target.value }))}
                    disabled={!!editingId}
                    className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors disabled:opacity-50"
                  />
                </div>
                <div className="space-y-1 flex-1">
                  <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                    Minor <span className="text-s-danger">*</span>
                  </label>
                  <input
                    type="text" placeholder="0001"
                    value={form.minor}
                    onChange={(e) => setForm((p) => ({ ...p, minor: e.target.value }))}
                    disabled={!!editingId}
                    className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors disabled:opacity-50"
                  />
                </div>
              </div>
              <p className="font-mono text-[10px] text-s-muted leading-relaxed">
                {editingId
                  ? "The iBeacon identity is the key and can't be changed. To re-key, delete and register again."
                  : <>Major / minor must match exactly what the beacon broadcasts (e.g. <span className="text-s-text">0001</span>, zero-padded).</>}
              </p>

              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  Person ID <span className="text-s-danger">*</span>
                </label>
                <input
                  type="text" placeholder="guard-001"
                  value={form.person_id}
                  onChange={(e) => setForm((p) => ({ ...p, person_id: e.target.value }))}
                  className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                />
              </div>
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Type</label>
                <select
                  value={form.person_type}
                  onChange={(e) => setForm((p) => ({ ...p, person_type: e.target.value as PersonType }))}
                  className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text focus:outline-none focus:border-s-accent transition-colors capitalize"
                >
                  {PERSON_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  Label <span className="text-s-danger">*</span>
                </label>
                <input
                  type="text" placeholder="Guard Alpha"
                  value={form.label}
                  onChange={(e) => setForm((p) => ({ ...p, label: e.target.value }))}
                  className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                />
              </div>

              {formError && (
                <p className="font-mono text-[10px] text-s-danger leading-relaxed">{formError}</p>
              )}
            </div>
            <div className="flex gap-2 px-5 py-4 border-t border-s-border">
              <button onClick={closeModal} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
              <button onClick={handleSave} disabled={saving} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
                {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                {saving ? "Saving…" : editingId ? "Save Changes" : "Register Beacon"}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
