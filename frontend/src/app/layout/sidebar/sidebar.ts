import { Component, signal } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AgentService } from '../../services/agent.service';
import { TaskProgressService } from '../../services/task-progress.service';

type ShutdownState = 'idle' | 'confirming' | 'shutting_down' | 'done' | 'error';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  shutdownState = signal<ShutdownState>('idle');
  hasActiveAnalysis = signal(false);

  constructor(
    private agentService: AgentService,
    private taskProgress: TaskProgressService,
  ) {}

  onShutdownClick(): void {
    this.taskProgress.getActiveTasks().subscribe({
      next: (tasks) => {
        this.hasActiveAnalysis.set(tasks.length > 0);
        this.shutdownState.set('confirming');
      },
      error: () => {
        // If we can't reach the backend, assume no active analyses
        this.hasActiveAnalysis.set(false);
        this.shutdownState.set('confirming');
      },
    });
  }

  onCancelShutdown(): void {
    this.shutdownState.set('idle');
  }

  onConfirmShutdown(): void {
    this.shutdownState.set('shutting_down');
    this.agentService.shutdown().subscribe({
      next: () => this.shutdownState.set('done'),
      error: () => this.shutdownState.set('error'),
    });
  }
}
