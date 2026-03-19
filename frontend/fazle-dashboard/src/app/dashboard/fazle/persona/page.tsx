'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { usePersona, useUpdatePersona } from '@/hooks/use-persona';
import { Save, UserCog } from 'lucide-react';

const personaSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  tone: z.string().min(1, 'Tone is required'),
  language: z.string().min(1, 'Language is required'),
  speaking_style: z.string().min(1, 'Speaking style is required'),
  knowledge_notes: z.string(),
});

type PersonaFormData = z.infer<typeof personaSchema>;

export default function PersonaPage() {
  const { data: persona, isLoading } = usePersona();
  const updateMutation = useUpdatePersona();
  const [saved, setSaved] = React.useState(false);

  const { register, handleSubmit, reset, formState: { errors, isDirty } } = useForm<PersonaFormData>({
    resolver: zodResolver(personaSchema),
  });

  React.useEffect(() => {
    if (persona) {
      reset(persona);
    }
  }, [persona, reset]);

  const onSubmit = async (data: PersonaFormData) => {
    await updateMutation.mutateAsync(data);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Persona Editor</h2>
        <p className="text-muted-foreground">Configure Fazle AI personality and behavior.</p>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <UserCog className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle>AI Persona Configuration</CardTitle>
              <CardDescription>Define how Fazle AI speaks, thinks, and behaves.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" {...register('name')} placeholder="Fazle" />
              {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="tone">Tone</Label>
                <Input id="tone" {...register('tone')} placeholder="friendly, professional" />
                {errors.tone && <p className="text-sm text-destructive">{errors.tone.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="language">Language</Label>
                <Input id="language" {...register('language')} placeholder="English" />
                {errors.language && <p className="text-sm text-destructive">{errors.language.message}</p>}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="speaking_style">Speaking Style</Label>
              <Textarea
                id="speaking_style"
                rows={3}
                {...register('speaking_style')}
                placeholder="Concise and clear, uses analogies..."
              />
              {errors.speaking_style && (
                <p className="text-sm text-destructive">{errors.speaking_style.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="knowledge_notes">Knowledge Notes</Label>
              <Textarea
                id="knowledge_notes"
                rows={6}
                {...register('knowledge_notes')}
                placeholder="Additional knowledge and context..."
              />
            </div>

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={updateMutation.isPending || !isDirty}>
                <Save className="mr-2 h-4 w-4" />
                {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
              </Button>
              {saved && (
                <span className="text-sm text-green-600 dark:text-green-400">
                  Persona saved successfully!
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
