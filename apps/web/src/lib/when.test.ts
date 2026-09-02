import { describe, expect, it } from 'vitest';
import { exactly, timeAgo } from './when';

const NOW = new Date('2026-09-01T12:00:00Z');

function ago(milliseconds: number): string {
	return timeAgo(new Date(NOW.getTime() - milliseconds).toISOString(), NOW);
}

describe('timeAgo', () => {
	it('says just now rather than counting seconds', () => {
		// A number that changes while you are reading it is noise.
		expect(ago(0)).toBe('just now');
		expect(ago(45_000)).toBe('just now');
	});

	it('climbs to the largest unit that fits', () => {
		expect(ago(5 * 60_000)).toContain('minute');
		expect(ago(3 * 60 * 60_000)).toContain('hour');
		expect(ago(2 * 24 * 60 * 60_000)).toContain('day');
		expect(ago(3 * 7 * 24 * 60 * 60_000)).toContain('week');
		expect(ago(400 * 24 * 60 * 60_000)).toContain('year');
	});

	it('is a function of its inputs, not of the clock', () => {
		const iso = new Date(NOW.getTime() - 3 * 60 * 60_000).toISOString();

		expect(timeAgo(iso, NOW)).toBe(timeAgo(iso, NOW));
	});

	it('says nothing at all about a timestamp it cannot read', () => {
		// Empty rather than "Invalid Date", which is a bug report shown to a
		// user who cannot act on it.
		expect(timeAgo('not a date', NOW)).toBe('');
		expect(exactly('not a date')).toBe('');
	});
});
