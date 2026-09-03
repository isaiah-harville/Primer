import { toast } from '@sivir-ui/svelte';

/**
 * Backend-failure notifications: shown as a toast when they happen, and kept
 * here afterward so a person who was away from the screen when one fired can
 * still find it. The toast library already discards a toast once it is
 * dismissed - by design, for a transient UI - so the record of what actually
 * went wrong lives here instead.
 */

export type NotificationType = 'success' | 'error' | 'warning' | 'info';

export interface NotificationEntry {
	id: number;
	type: NotificationType;
	title: string;
	description?: string;
	at: number;
	read: boolean;
}

//: Bounded so a deployment having a bad day does not grow this without
//: limit; the newest ones are what anyone actually wants to see.
const MAX_HISTORY = 50;

let nextId = 0;
let history = $state<NotificationEntry[]>([]);

/** Shows a toast and records it, newest first. */
export function notify(type: NotificationType, title: string, description?: string): void {
	toast[type](title, description ? { description } : undefined);
	nextId += 1;
	history = [
		{ id: nextId, type, title, description, at: Date.now(), read: false },
		...history,
	].slice(0, MAX_HISTORY);
}

export function notifications(): NotificationEntry[] {
	return history;
}

export function unreadCount(): number {
	return history.filter((entry) => !entry.read).length;
}

export function markAllRead(): void {
	if (history.every((entry) => entry.read)) return;
	history = history.map((entry) => (entry.read ? entry : { ...entry, read: true }));
}
