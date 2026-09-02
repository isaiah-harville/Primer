/**
 * Saying when something happened, briefly.
 *
 * A conversation list is read to find one thread among many, and the useful
 * part of a timestamp there is how long ago it was, not the minute it
 * happened. The exact time is kept on the element's `title` for the times
 * when the minute is what someone wants.
 */

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
	['year', 365 * 24 * 60 * 60 * 1000],
	['month', 30 * 24 * 60 * 60 * 1000],
	['week', 7 * 24 * 60 * 60 * 1000],
	['day', 24 * 60 * 60 * 1000],
	['hour', 60 * 60 * 1000],
	['minute', 60 * 1000],
];

/**
 * How long ago `iso` was, in words.
 *
 * `now` is a parameter so this is a function of its inputs rather than of
 * the clock, which is what makes it testable and what keeps a server-render
 * and the browser's first render from disagreeing about the same string.
 */
export function timeAgo(iso: string, now: Date = new Date()): string {
	const then = new Date(iso);
	if (Number.isNaN(then.getTime())) return '';

	const elapsed = now.getTime() - then.getTime();
	// Anything under a minute is "just now" rather than a count of seconds:
	// a number that changes while you are reading it is noise.
	if (elapsed < UNITS[UNITS.length - 1][1]) return 'just now';

	const format = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
	for (const [unit, size] of UNITS) {
		if (Math.abs(elapsed) >= size) {
			return format.format(-Math.round(elapsed / size), unit);
		}
	}
	return 'just now';
}

/** The whole timestamp, for the tooltip behind the short form. */
export function exactly(iso: string): string {
	const when = new Date(iso);
	return Number.isNaN(when.getTime()) ? '' : when.toLocaleString();
}
