import { describe, expect, it } from 'vitest';
import { ApiError, asProblem } from './client';

/**
 * Reading an error body that may not be what it claims.
 *
 * The services all answer in the contract's shape now. This is the guarantee
 * that one which does not - an older build, a gateway, a framework's own
 * validation body - cannot put nonsense in front of a user. It used to: the
 * body was cast and trusted, so a `detail` that was a list of objects became
 * the message "[object Object]".
 */

describe('reading an error body', () => {
	it('keeps a well formed problem document intact', () => {
		const problem = asProblem(
			{
				code: 'not_found',
				title: 'Library not found',
				status: 404,
				detail: 'No library with that identifier is available to you.',
				request_id: 'abc123',
			},
			404,
		);

		expect(problem.code).toBe('not_found');
		expect(problem.detail).toBe('No library with that identifier is available to you.');
		expect(problem.request_id).toBe('abc123');
	});

	it('does not let a structured detail become a message', () => {
		// The regression, in the exact shape FastAPI produces.
		const problem = asProblem(
			{ detail: [{ type: 'string_too_long', loc: ['body', 'name'], msg: 'too long' }] },
			422,
		);

		expect(new ApiError(problem).message).not.toContain('[object Object]');
		expect(problem.detail).toBe('The server replied with 422.');
	});

	it('takes the status from the response, not from the body', () => {
		// They disagree only when the body is not what it says it is, and the
		// response is the half that actually happened.
		expect(asProblem({ status: 200 }, 502).status).toBe(502);
	});

	it('survives a body that is not an object at all', () => {
		expect(asProblem(null, 500).detail).toBe('The server replied with 500.');
		expect(asProblem('gateway timeout', 504).code).toBe('unexpected_response');
	});

	it('gives ApiError a usable message whatever arrived', () => {
		// Callers put this straight on screen, so it has to be words.
		const error = new ApiError(asProblem({ detail: { nested: true } }, 500));
		expect(error.message).toBe('The server replied with 500.');
		expect(error.status).toBe(500);
	});
});
