interface CommonJsModuleLike {
	exports?: unknown;
}

interface ChromeRuntimeLastError {
	message?: string;
}

interface ChromeRuntimeLike {
	lastError?: ChromeRuntimeLastError | null;
	sendMessage<TResponse = unknown>(
		message: unknown,
		callback?: (response: TResponse) => void,
	): void;
}

interface ChromeLike {
	runtime: ChromeRuntimeLike;
}

declare const module: CommonJsModuleLike | undefined;

declare const chrome: ChromeLike;
