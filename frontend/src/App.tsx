// Главный экран Stego-Guard: режим -> загрузка -> результат.
// Связывает UploadZone, ResultCard и API-клиент гейтвея.
import { useState } from 'react';
import {
  Center, Container, Loader, SegmentedControl, Stack, Text, TextInput, Title,
} from '@mantine/core';
import UploadZone from './components/UploadZone';
import ResultCard from './components/ResultCard';
import { embedDocument, verifyDocument } from './api/client';
import type { EmbedResult, Mode, VerifyResponse } from './types/api';

type ResultState =
  | { kind: 'embed'; data: EmbedResult; fileName: string }
  | { kind: 'verify'; data: VerifyResponse };

export default function App() {
  const [mode, setMode] = useState<Mode>('embed');
  const [userId, setUserId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ResultState | null>(null);

  const handleFile = async (file: File) => {
    setError('');
    setResult(null);
    setBusy(true);
    try {
      if (mode === 'embed') {
        if (!userId.trim()) {
          setError('Введите ID пользователя/участка');
          return;
        }
        const data = await embedDocument(file, userId.trim());
        setResult({ kind: 'embed', data, fileName: file.name });
      } else {
        const data = await verifyDocument(file);
        setResult({ kind: 'verify', data });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Неизвестная ошибка');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>Stego-Guard</Title>
          <Text c="dimmed">Защита и верификация цифровых документов</Text>
        </div>

        <SegmentedControl
          fullWidth
          size="md"
          value={mode}
          onChange={(v) => {
            setMode(v as Mode);
            setResult(null);
            setError('');
          }}
          data={[
            { value: 'embed', label: '🔒 Защитить документ' },
            { value: 'verify', label: '🔍 Проверить документ' },
          ]}
        />

        {mode === 'embed' && (
          <TextInput
            label="ID пользователя / участка"
            placeholder="например, UIK-42"
            value={userId}
            onChange={(e) => setUserId(e.currentTarget.value)}
            required
          />
        )}

        <UploadZone onFile={handleFile} />

        {busy && (
          <Center py="md">
            <Loader size="md" />
          </Center>
        )}

        {error && (
          <Text c="red" size="sm">
            ⚠️ {error}
          </Text>
        )}

        {result?.kind === 'embed' && (
          <ResultCard kind="embed" result={result.data} fileName={result.fileName} />
        )}
        {result?.kind === 'verify' && (
          <ResultCard kind="verify" result={result.data} />
        )}
      </Stack>
    </Container>
  );
}