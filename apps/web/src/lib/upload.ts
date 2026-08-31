import type { DeploymentCapabilities } from './api/types';

/**
 * Deciding whether a file is worth sending.
 *
 * This is a courtesy, not a control. The server checks the bytes and rejects
 * a file whose contents disagree with its name; this only saves the user
 * from uploading a hundred megabytes to be told no. Any rule here that the
 * server does not also enforce would be a rule that does not exist.
 */

export interface Rejection {
	code: 'unsupported_extension' | 'too_large' | 'empty';
	message: string;
}

export function describeAccepted(capabilities: DeploymentCapabilities): string {
	const names: Record<string, string> = {
		'.pdf': 'PDF',
		'.docx': 'DOCX',
		'.pptx': 'PPTX',
		'.md': 'Markdown',
		'.markdown': 'Markdown',
		'.txt': 'text',
	};
	const labels = capabilities.supported_extensions.map((ext) => names[ext] ?? ext);
	return [...new Set(labels)].join(', ');
}

export function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	const units = ['KB', 'MB', 'GB'];
	let value = bytes / 1024;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

export function rejectionFor(file: File, capabilities: DeploymentCapabilities): Rejection | null {
	const dot = file.name.lastIndexOf('.');
	const extension = dot === -1 ? '' : file.name.slice(dot).toLowerCase();

	if (!capabilities.supported_extensions.includes(extension)) {
		return {
			code: 'unsupported_extension',
			message: `${file.name} is not a supported format. Primer accepts ${describeAccepted(capabilities)} files.`,
		};
	}
	if (file.size === 0) {
		return { code: 'empty', message: `${file.name} is empty.` };
	}
	if (file.size > capabilities.max_upload_bytes) {
		return {
			code: 'too_large',
			message: `${file.name} is ${formatBytes(file.size)}, over the ${formatBytes(capabilities.max_upload_bytes)} limit.`,
		};
	}
	return null;
}
