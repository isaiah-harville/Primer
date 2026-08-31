import { describe, expect, it } from 'vitest';
import type { IngestionStatus } from './api/types';
import { describeStatus, isTerminal, pollDelayMs } from './status';

const ALL: IngestionStatus[] = [
	'queued',
	'parsing',
	'chunking',
	'embedding',
	'indexing',
	'ready',
	'failed',
	'unsupported',
	'cancelled',
	'deleting',
	'deleted',
];

describe('status descriptions', () => {
	it('gives every status words, not just a colour', () => {
		// Colour alone is invisible to a screen reader and ambiguous to
		// anyone who cannot distinguish the shades.
		for (const status of ALL) {
			const described = describeStatus(status);
			expect(described.label.length).toBeGreaterThan(0);
			expect(described.detail.length).toBeGreaterThan(0);
		}
	});

	it('distinguishes the four stages of processing', () => {
		// A user waiting on a slow document needs to know which stage it is
		// stuck in; "processing" for all four hides that.
		const labels = ['parsing', 'chunking', 'embedding', 'indexing'].map(
			(s) => describeStatus(s as IngestionStatus).label,
		);
		expect(new Set(labels).size).toBe(4);
	});

	it('prefers the server detail when there is one', () => {
		// "no text layer, and OCR is off" is more useful than our generic text.
		const described = describeStatus('unsupported', 'This PDF has no text layer.');
		expect(described.detail).toBe('This PDF has no text layer.');
	});

	it('knows which states stop polling', () => {
		expect(isTerminal('ready')).toBe(true);
		expect(isTerminal('failed')).toBe(true);
		expect(isTerminal('unsupported')).toBe(true);
		expect(isTerminal('parsing')).toBe(false);
		expect(isTerminal('queued')).toBe(false);
	});

	it('backs off, and caps', () => {
		// A ten-minute document should not cost six hundred requests, and a
		// finished one should be noticed promptly.
		expect(pollDelayMs(0)).toBe(1000);
		expect(pollDelayMs(3)).toBe(8000);
		expect(pollDelayMs(10)).toBe(15000);
		expect(pollDelayMs(50)).toBe(15000);
	});
});
