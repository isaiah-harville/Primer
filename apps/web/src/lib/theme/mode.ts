/**
 * Light/dark selection.
 *
 * The whole theme keys off a `dark` class on the document element, so all
 * this does is decide when to put it there. Three states rather than two: a
 * reader who has never chosen should follow the system, and that is not the
 * same as having chosen light.
 */

export type Mode = 'light' | 'dark' | 'system';

export const MODE_STORAGE_KEY = 'primer:theme';

export function isMode(value: unknown): value is Mode {
	return value === 'light' || value === 'dark' || value === 'system';
}

/** What `system` currently resolves to. */
export function prefersDark(): boolean {
	return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function resolve(mode: Mode, systemIsDark: boolean): boolean {
	return mode === 'system' ? systemIsDark : mode === 'dark';
}

export function readStoredMode(): Mode {
	try {
		// Reached through `window` deliberately. Node 24 defines a global
		// `localStorage` of its own, which shadows the browser's under a test
		// runner and is not a Storage at all.
		const stored = window.localStorage.getItem(MODE_STORAGE_KEY);
		return isMode(stored) ? stored : 'system';
	} catch {
		// Storage can throw outright when the browser is set to block site
		// data. A theme is not worth failing a page load over.
		return 'system';
	}
}

export function storeMode(mode: Mode): void {
	try {
		window.localStorage.setItem(MODE_STORAGE_KEY, mode);
	} catch {
		// Nothing to do: the choice lasts for this page instead.
	}
}

export function applyMode(mode: Mode): void {
	document.documentElement.classList.toggle('dark', resolve(mode, prefersDark()));
}
