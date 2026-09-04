import { describe, expect, it } from 'vitest';
import type { ChatModel } from '$lib/api/types';
import { qualify, unqualify } from './models';

/**
 * Naming a model so a question reaches the right machine.
 *
 * A deployment can hold several providers, and model names are not unique
 * across them - two endpoints serving `llama3.1:8b` is ordinary. If the
 * picker's value were a bare model name, choosing the local one and the
 * hosted one would be indistinguishable, and questions meant for a private
 * machine could be answered by a paid account instead.
 */

function model(id: string, provider_id?: string): ChatModel {
	return { id, default: false, provider_id: provider_id ?? null, provider_name: null };
}

describe('qualifying a model', () => {
	it('names the provider alongside the model', () => {
		expect(qualify(model('llama3.1:8b', 'abc-123'))).toBe('abc-123:llama3.1:8b');
	});

	it('tells two providers serving the same model apart', () => {
		// The whole reason the pair is the name.
		expect(qualify(model('llama3.1:8b', 'workstation'))).not.toBe(
			qualify(model('llama3.1:8b', 'server')),
		);
	});

	it('leaves a model with no provider as its bare name', () => {
		expect(qualify(model('gpt-4o-mini'))).toBe('gpt-4o-mini');
	});

	it('is empty for no model, so nothing is sent', () => {
		expect(qualify(undefined)).toBe('');
	});
});

describe('splitting it back apart', () => {
	it('recovers both halves', () => {
		expect(unqualify('abc-123:llama3.1:8b')).toEqual({
			provider_id: 'abc-123',
			model: 'llama3.1:8b',
		});
	});

	it('splits on the first separator only', () => {
		// Model names contain colons - `llama3.1:8b` is the common case - so
		// splitting on the last one, or on all of them, loses the tag.
		expect(unqualify('p:qwen2.5:3b-instruct').model).toBe('qwen2.5:3b-instruct');
	});

	it('round-trips whatever was qualified', () => {
		const chosen = model('qwen2.5:3b-instruct', 'deadbeef');
		expect(unqualify(qualify(chosen))).toEqual({
			provider_id: 'deadbeef',
			model: 'qwen2.5:3b-instruct',
		});
	});

	it('treats a bare name as a model with no provider', () => {
		// A deployment with only its own provider never qualifies anything.
		expect(unqualify('gpt-4o-mini')).toEqual({ model: 'gpt-4o-mini' });
	});

	it('sends nothing at all for an empty choice', () => {
		// Which is what asks for the deployment's default.
		expect(unqualify('')).toEqual({});
	});
});
