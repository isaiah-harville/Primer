import { describe, expect, it } from 'vitest';
import type { MessageSummary } from '$lib/api/types';
import { turnsFrom } from './transcript';

function message(overrides: Partial<MessageSummary>): MessageSummary {
	return {
		id: 'm',
		conversation_id: 'c',
		role: 'user',
		state: 'completed',
		content: '',
		citations: [],
		error_code: null,
		created_at: '2026-09-01T12:00:00Z',
		...overrides,
	};
}

const question = (content: string) => message({ role: 'user', content });
const answer = (content: string, overrides: Partial<MessageSummary> = {}) =>
	message({ role: 'assistant', content, ...overrides });

describe('turnsFrom', () => {
	it('pairs each answer with the question before it', () => {
		const turns = turnsFrom([
			question('First?'),
			answer('First.'),
			question('Second?'),
			answer('Second.'),
		]);

		expect(turns.map((turn) => [turn.question, turn.stream.text])).toEqual([
			['First?', 'First.'],
			['Second?', 'Second.'],
		]);
	});

	it('shows a question that was never answered', () => {
		// The stream died, or the tab closed. Dropping it would lose the
		// evidence that it was ever asked.
		const turns = turnsFrom([question('Unanswered?')]);

		expect(turns).toHaveLength(1);
		expect(turns[0].stream.text).toBe('');
	});

	it('keeps an answer that has no question in front of it', () => {
		const turns = turnsFrom([answer('Out of nowhere.')]);

		expect(turns).toEqual([expect.objectContaining({ question: '' })]);
		expect(turns[0].stream.text).toBe('Out of nowhere.');
	});

	it('does not let one answer overwrite another', () => {
		const turns = turnsFrom([question('One?'), answer('First.'), answer('Second.')]);

		expect(turns.map((turn) => turn.stream.text)).toEqual(['First.', 'Second.']);
	});

	it('reads a failed answer back as failed, with what it wrote', () => {
		const turns = turnsFrom([
			question('What?'),
			answer('Half an ans', { state: 'failed', error_code: 'context_exhausted' }),
		]);

		expect(turns[0].stream.error).toEqual({ code: 'context_exhausted', detail: null });
		expect(turns[0].stream.text).toBe('Half an ans');
	});

	it('carries the citations an answer was stored with', () => {
		const citation = {
			document_id: 'd',
			document_version_id: 'v',
			chunk_id: 'k',
			locator: null,
			excerpt: 'The measured result.',
		};

		const turns = turnsFrom([
			question('What?'),
			answer('Grounded [1].', { citations: [citation] }),
		]);

		expect(turns[0].stream.citations).toEqual([citation]);
	});
});
