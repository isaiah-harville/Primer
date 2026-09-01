import { afterEach, describe, expect, it, vi } from 'vitest';
import { isMode, MODE_STORAGE_KEY, readStoredMode, resolve, storeMode } from './mode';

/**
 * The test environment supplies no `localStorage` of its own, so these
 * install one. That is not a workaround: the point of these tests is what
 * happens when storage answers oddly or refuses outright, which a real
 * working store could not be made to do anyway.
 */
function useStorage(store: Partial<Storage>): void {
	vi.stubGlobal('window', { ...globalThis.window, localStorage: store });
}

function workingStorage(): Storage {
	const entries = new Map<string, string>();
	return {
		getItem: (key: string) => entries.get(key) ?? null,
		setItem: (key: string, value: string) => void entries.set(key, value),
		removeItem: (key: string) => void entries.delete(key),
		clear: () => entries.clear(),
		key: (index: number) => [...entries.keys()][index] ?? null,
		get length() {
			return entries.size;
		},
	};
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('resolve', () => {
	it('follows the system only when the mode is system', () => {
		expect(resolve('system', true)).toBe(true);
		expect(resolve('system', false)).toBe(false);
	});

	// The whole point of choosing: a reader who picked light keeps light on a
	// machine that switches itself to dark at sunset.
	it('ignores the system once a mode has been chosen', () => {
		expect(resolve('light', true)).toBe(false);
		expect(resolve('dark', false)).toBe(true);
	});
});

describe('isMode', () => {
	it('accepts the three modes and nothing else', () => {
		expect(isMode('light')).toBe(true);
		expect(isMode('dark')).toBe(true);
		expect(isMode('system')).toBe(true);
		expect(isMode('Dark')).toBe(false);
		expect(isMode(null)).toBe(false);
		expect(isMode(undefined)).toBe(false);
	});
});

describe('readStoredMode', () => {
	it('returns a stored choice', () => {
		const storage = workingStorage();
		storage.setItem(MODE_STORAGE_KEY, 'dark');
		useStorage(storage);
		expect(readStoredMode()).toBe('dark');
	});

	it('falls back to system when nothing is stored', () => {
		useStorage(workingStorage());
		expect(readStoredMode()).toBe('system');
	});

	// Anything could be under this key: another tool on the same origin, or
	// a value Primer itself wrote in an older version.
	it('falls back to system when the stored value is not a mode', () => {
		const storage = workingStorage();
		storage.setItem(MODE_STORAGE_KEY, 'sepia');
		useStorage(storage);
		expect(readStoredMode()).toBe('system');
	});

	// Browsers set to block site data throw on access rather than returning
	// null, so this is a real state and not a hypothetical one.
	it('falls back to system when storage throws', () => {
		useStorage({
			getItem: () => {
				throw new Error('site data blocked');
			},
		});
		expect(readStoredMode()).toBe('system');
	});
});

describe('storeMode', () => {
	it('round-trips through storage', () => {
		useStorage(workingStorage());
		storeMode('light');
		expect(readStoredMode()).toBe('light');
	});

	// Losing the preference is acceptable; taking the page down with it is
	// not, so the write failing must stay silent.
	it('does not throw when storage refuses the write', () => {
		useStorage({
			setItem: () => {
				throw new Error('site data blocked');
			},
		});
		expect(() => storeMode('dark')).not.toThrow();
	});
});
