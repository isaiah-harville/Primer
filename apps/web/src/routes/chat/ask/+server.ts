import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

/**
 * Proxies the chat stream from the browser to the Chat service.
 *
 * The body is piped through untouched rather than collected and re-sent: a
 * stream buffered here would arrive all at once, which defeats the point of
 * streaming it.
 */
export const POST: RequestHandler = async ({ request, fetch }) => {
	const headers = new Headers({ 'Content-Type': 'application/json' });
	for (const name of ['x-auth-request-user', 'x-auth-request-email', 'x-auth-request-groups']) {
		const value = request.headers.get(name);
		if (value) headers.set(name, value);
	}

	const upstream = await fetch(
		`${env.PRIMER_CHAT_URL ?? 'http://localhost:8100'}/api/v1/conversations`,
		{ method: 'POST', headers, body: await request.text() },
	);

	return new Response(upstream.body, {
		status: upstream.status,
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			// Several proxies buffer by default, which would hold every token
			// until the answer finished.
			'X-Accel-Buffering': 'no',
		},
	});
};
