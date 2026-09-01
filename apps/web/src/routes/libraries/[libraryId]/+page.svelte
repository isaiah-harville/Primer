<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import { RefreshCw, Trash2 } from '@lucide/svelte';
	import { Alert, Breadcrumb, Button, Spinner } from '@sivir-ui/svelte';
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
	let ready = $derived(data.documents.filter((doc) => doc.status === 'ready').length);
	// Anything finished that is not ready needs a person: a failed parse, an
	// unreadable scan. Counted separately so it is visible without reading
	// every row.
	let problems = $derived(
		data.documents.filter((doc) => isTerminal(doc.status) && doc.status !== 'ready').length
	);

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

<div class="flex flex-wrap items-end justify-between gap-4">
	<div class="min-w-0">
		<nav aria-label="Breadcrumb">
			<Breadcrumb.Root>
				<Breadcrumb.Item href="/libraries">Libraries</Breadcrumb.Item>
				<Breadcrumb.Separator />
				<!--
				  The last crumb is plain text, not a link: a link to the page
				  you are already on is a dead end for anyone navigating by
				  links.
				-->
				<span aria-current="page" class="truncate font-semibold text-foreground">
					{data.library.name}
				</span>
			</Breadcrumb.Root>
		</nav>

		<h1 class="mt-2 truncate text-xl font-semibold tracking-[-0.02em]">{data.library.name}</h1>

		<!--
		  A counted summary rather than a bare total: "3 documents" hides that
		  one of them failed, which is the thing worth acting on.
		-->
		<p class="mt-1 flex flex-wrap items-center gap-x-2 font-mono text-[11px] uppercase
			tracking-[0.09em] text-muted-foreground">
			<span>{data.documents.length} {data.documents.length === 1 ? 'document' : 'documents'}</span>
			{#if ready > 0}<span aria-hidden="true">·</span><span>{ready} ready</span>{/if}
			{#if pending.length > 0}
				<span aria-hidden="true">·</span>
				<span class="flex items-center gap-1.5 text-foreground">
					<Spinner size={11} aria-hidden="true" />
					{pending.length} processing
				</span>
			{/if}
			{#if problems > 0}
				<span aria-hidden="true">·</span>
				<span class="text-error">{problems} needing attention</span>
			{/if}
		</p>
	</div>

	{#if data.capabilities.ingestion_available}
		<UploadDropzone capabilities={data.capabilities} onupload={upload} />
	{/if}
</div>

{#if !data.capabilities.ingestion_available}
	<!--
	  Warning, not error: nothing has failed, but an upload here would sit in
	  the queue forever and it is better to say so before the drop.
	-->
	<Alert.Root variant="warning" class="mt-6">
		<Alert.Title>No ingestion workers are running</Alert.Title>
		<Alert.Description>
			Uploads would stay queued indefinitely, so documents cannot be added until a worker is
			configured.
		</Alert.Description>
	</Alert.Root>
{/if}

{#if uploadError}
	<Alert.Root variant="error" class="mt-4">
		<Alert.Description>{uploadError}</Alert.Description>
	</Alert.Root>
{/if}

{#if form?.error}
	<Alert.Root variant="error" class="mt-4">
		<Alert.Description>{form.error}</Alert.Description>
	</Alert.Root>
{/if}

<!--
  Status changes happen without the user acting, so they are announced
  politely rather than interrupting whatever they are reading.
-->
<p class="sr-only" aria-live="polite">{announcement}</p>

{#if data.documents.length === 0 && uploading.length === 0}
	<div class="mt-16 text-center">
		<p class="font-medium">No documents yet</p>
		<p class="mx-auto mt-1.5 max-w-md text-sm text-muted-foreground">
			Add a file above. Once it has been read and indexed it becomes searchable, and answers can
			cite it.
		</p>
	</div>
{:else}
	<!--
	  A table, because these rows are compared down columns: which are ready,
	  which are large, which failed. The header row is what makes that
	  possible, and it is why this is not the list of cards the libraries
	  themselves get.
	-->
	<div class="mt-8 overflow-x-auto">
		<!--
		  Fixed layout, so the columns keep the widths set below instead of
		  being sized by whatever happens to be in them. Filenames are long
		  and would otherwise take the whole row on one page and none of it on
		  the next.
		-->
		<table class="w-full min-w-[46rem] table-fixed border-collapse text-sm">
			<caption class="sr-only">Documents in {data.library.name}</caption>
			<thead>
				<tr class="border-y border-border">
					{#each [{ label: 'Document', width: 'w-auto' }, { label: 'Size', width: 'w-24' }, { label: 'Status', width: 'w-[22rem]' }] as column (column.label)}
						<th
							scope="col"
							class="{column.width} px-3 py-2 text-left font-mono text-[10px] font-medium
								uppercase tracking-[0.09em] text-muted-foreground"
						>
							{column.label}
						</th>
					{/each}
					<th scope="col" class="w-24 px-3 py-2">
						<span class="sr-only">Actions</span>
					</th>
				</tr>
			</thead>
			<tbody>
				{#each uploading as name (name)}
					<tr class="border-b border-border text-muted-foreground">
						<td class="px-3 py-2.5 font-mono">{name}</td>
						<td class="px-3 py-2.5"></td>
						<td class="px-3 py-2.5">
							<span class="flex items-center gap-2">
								<Spinner size={13} aria-hidden="true" />
								Uploading…
							</span>
						</td>
						<td class="px-3 py-2.5"></td>
					</tr>
				{/each}

				{#each data.documents as document (document.id)}
					<tr class="group border-b border-border transition-colors hover:bg-muted/60">
						<td class="px-3 py-2.5">
							<a
								href="/libraries/{data.library.id}/documents/{document.id}/content"
								class="block truncate font-mono hover:underline focus-visible:outline-none
									focus-visible:shadow-[var(--focus-ring)]"
							>
								{document.filename}
							</a>
						</td>
						<td class="whitespace-nowrap px-3 py-2.5 tabular-nums text-muted-foreground">
							{formatBytes(document.byte_size)}
						</td>
						<td class="px-3 py-2.5">
							<DocumentStatus status={document.status} detail={document.status_detail} />
						</td>
						<td class="px-3 py-2.5">
							<div class="flex items-center justify-end gap-1">
								<form method="POST" action="?/reindex" use:enhance>
									<input type="hidden" name="id" value={document.id} />
									<Button
										type="submit"
										variant="ghost"
										size="icon"
										class="text-muted-foreground"
										title="Reindex"
									>
										<RefreshCw size={14} aria-hidden="true" />
										<span class="sr-only">Reindex {describe(document)}</span>
									</Button>
								</form>
								<form
									method="POST"
									action="?/delete"
									use:enhance={({ cancel }) => {
										if (!confirm(`Delete ${document.filename}?`)) cancel();
									}}
								>
									<input type="hidden" name="id" value={document.id} />
									<Button
										type="submit"
										variant="ghost"
										size="icon"
										class="text-muted-foreground"
										title="Delete"
									>
										<Trash2 size={14} aria-hidden="true" />
										<span class="sr-only">Delete {describe(document)}</span>
									</Button>
								</form>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
