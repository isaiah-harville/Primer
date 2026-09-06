import { describe, expect, it } from 'vitest';
import { downloadHeaders } from './download';

describe('downloadHeaders', () => {
	const upstream = (entries: Record<string, string>) => new Headers(entries);

	it('carries across what describes the bytes', () => {
		const headers = downloadHeaders(
			upstream({
				'content-type': 'application/pdf',
				'content-disposition': "attachment; filename*=UTF-8''paper.pdf",
				'content-length': '2048',
			}),
		);

		expect(headers.get('content-type')).toBe('application/pdf');
		expect(headers.get('content-disposition')).toBe("attachment; filename*=UTF-8''paper.pdf");
		expect(headers.get('content-length')).toBe('2048');
	});

	/**
	 * The reason this function exists rather than a spread of the upstream
	 * headers. These are files other people uploaded, served from the
	 * application's own origin, so anything the browser agreed to render in
	 * place - an uploaded HTML file above all - would run as Primer, with
	 * the session of whoever opened it.
	 */
	it('does not turn an attachment into something rendered in place', () => {
		const headers = downloadHeaders(
			upstream({
				'content-type': 'text/html',
				'content-disposition': 'attachment; filename="notes.html"',
			}),
		);

		expect(headers.get('content-disposition')).toContain('attachment');
	});

	it('leaves nothing about the download in a shared cache', () => {
		const headers = downloadHeaders(upstream({ 'content-type': 'application/pdf' }));

		expect(headers.get('cache-control')).toBe('private, no-store');
	});

	it('passes nothing else on', () => {
		const headers = downloadHeaders(
			upstream({
				'content-type': 'application/pdf',
				'set-cookie': 'session=secret',
				'x-internal-generation': '3',
			}),
		);

		expect([...headers.keys()].sort()).toEqual(['cache-control', 'content-type']);
	});

	it('omits a header the upstream did not send rather than sending it empty', () => {
		const headers = downloadHeaders(upstream({ 'content-type': 'application/pdf' }));

		expect(headers.has('content-length')).toBe(false);
		expect(headers.has('content-disposition')).toBe(false);
	});
});
