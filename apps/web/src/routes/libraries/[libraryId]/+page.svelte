<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import { PrimerApi } from '$lib/api/client';
	import type { DocumentSummary } from '$lib/api/types';
	import DocumentStatus from '$lib/components/DocumentStatus.svelte';
	import UploadDropzone from '$lib/components/UploadDropzone.svelte';
	import { isTerminal, pollDelayMs } from '$lib/status';
	import { formatBytes } from '$lib/upload';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const api = new PrimerApi();
	let uploading = $state<string[]>([]);
	let announcement = $state('');
	let uploadError = $state('');

	let pending = $derived(data.documents.filter((doc) => !isTerminal(doc.status)));

	async function upload(files: File[]) {
		uploadError = '';
		for (const file of files) {
			uploading = [...uploading, file.name];
			announcement = `Uploading ${file.name}.`;
			try {
				await api.upload(data.library.id, file);
				announcement = `${file.name} uploaded and queued.`;
			} catch (error) {
				uploadError = error instanceof Error ? error.message : `${file.name} could not be uploaded.`;
				announcement = uploadError;
			} finally {
				uploading = uploading.filter((name) => name !== file.name);
			}
		}
		await invalidateAll();
	}

	// Poll only while something is unfinished, backing off as it drags on: a
	// ten-minute document should not cost hundreds of requests, and a
	// finished one should stop costing anything at all.
	$effect(() => {
		if (pending.length === 0) return;
		let attempt = 0;
		let cancelled = false;

		const tick = async () => {
			if (cancelled) return;
			await invalidateAll();
			attempt += 1;
			if (!cancelled) timer = setTimeout(tick, pollDelayMs(attempt));
		};

		let timer = setTimeout(tick, pollDelayMs(attempt));
		return () => {
			cancelled = true;
			clearTimeout(timer);
		};
	});

	function describe(document: DocumentSummary): string {
		return `${document.filename}, ${formatBytes(document.byte_size)}`;
	}
</script>

<nav aria-label="Breadcrumb" class="crumbs">
	<a href="/libraries">Libraries</a> <span aria-hidden="true">/</span>
	<span aria-current="page">{data.library.name}</span>
</nav>

<h1>{data.library.name}</h1>

{#if data.capabilities.ingestion_available}
	<UploadDropzone capabilities={data.capabilities} onupload={upload} />
{:else}
	<p class="notice">
		This deployment has no ingestion workers configured, so uploads would stay queued
		indefinitely. Documents cannot be added until one is running.
	</p>
{/if}

{#if uploadError}
	<p class="error" role="alert">{uploadError}</p>
{/if}

<!--
  Status changes happen without the user acting, so they are announced
  politely rather than interrupting whatever they are reading.
-->
<p class="visually-hidden" aria-live="polite">{announcement}</p>

{#if data.documents.length === 0 && uploading.length === 0}
	<p class="empty">No documents yet.</p>
{:else}
	<table>
		<caption class="visually-hidden">Documents in {data.library.name}</caption>
		<thead>
			<tr><th scope="col">Document</th><th scope="col">Status</th><th scope="col">Actions</th></tr>
		</thead>
		<tbody>
			{#each uploading as name (name)}
				<tr><td>{name}</td><td>Uploading…</td><td></td></tr>
			{/each}
			{#each data.documents as document (document.id)}
				<tr>
					<td>
						<a href="/libraries/{data.library.id}/documents/{document.id}/content">
							{document.filename}
						</a>
						<span class="meta">{formatBytes(document.byte_size)}</span>
					</td>
					<td><DocumentStatus status={document.status} detail={document.status_detail} /></td>
					<td class="actions">
						<form method="POST" action="?/reindex" use:enhance>
							<input type="hidden" name="id" value={document.id} />
							<button type="submit">
								Reindex<span class="visually-hidden"> {describe(document)}</span>
							</button>
						</form>
						<form
							method="POST"
							action="?/delete"
							use:enhance={({ cancel }) => {
								if (!confirm(`Delete ${document.filename}?`)) cancel();
							}}
						>
							<input type="hidden" name="id" value={document.id} />
							<button type="submit" class="danger">
								Delete<span class="visually-hidden"> {describe(document)}</span>
							</button>
						</form>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
{/if}

{#if form?.error}
	<p class="error" role="alert">{form.error}</p>
{/if}

<style>
	.crumbs {
		font-size: 0.875rem;
		color: #475569;
		margin-bottom: 0.5rem;
	}
	.notice {
		background: #fef3c7;
		border-radius: 8px;
		padding: 0.75rem 1rem;
		color: #78350f;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		margin-top: 1.5rem;
	}
	th {
		text-align: left;
		font-size: 0.8125rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: #475569;
		border-bottom: 1px solid #e2e8f0;
		padding-bottom: 0.5rem;
	}
	td {
		padding: 0.75rem 0.5rem 0.75rem 0;
		border-bottom: 1px solid #f1f5f9;
		vertical-align: top;
	}
	.meta {
		display: block;
		color: #475569;
		font-size: 0.8125rem;
	}
	.actions {
		display: flex;
		gap: 0.5rem;
	}
	button {
		padding: 0.375rem 0.625rem;
		border-radius: 8px;
		border: 1px solid #cbd5e1;
		background: #f8fafc;
		font: inherit;
		font-size: 0.875rem;
		cursor: pointer;
	}
	.danger {
		color: #b91c1c;
	}
	.error {
		color: #b91c1c;
	}
	.empty {
		color: #475569;
	}
	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
