#include "MorphHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Misc/App.h"
#include "MorphOperative.h"
#include "MorphPlayerController.h"
#include "MorphShowcaseGameMode.h"

namespace
{
	const TCHAR* HelpLines[] = {
		TEXT("MOVE  WASD (camera relative)  Shift sprint  Ctrl/Caps walk toggle  F11 strafe/face-aim toggle  F10 stance"),
		TEXT("AIM   hold RMB / L lock, mouse on ground, M aim at target (Tab select, arrows+PgUp/PgDn move target)"),
		TEXT("MOVE+ Space jump  Q dash (input dir, root motion 2 m)  E blink"),
		TEXT("FIGHT LMB melee (click again for combo)  RMB tap fire / hold burst  R reload  1 cast dir  2 cast ground  3 cast self"),
		TEXT("HOLD  4 channel (X interrupt)  5 charge (release fires, C cancels)  6 deploy beacon  7 uplink (release early = cancel)"),
		TEXT("REACT H hit (cycles dir, Shift = back)  T stun  K knockback  U knockup  J knockdown (Shift = from behind)  N sleep/wake"),
		TEXT("LIFE  Del death (Shift = back impact)  Z respawn  G greet  V victory  B defeat  P dialogue (audio)  Enter resume  Backspace reset"),
		TEXT("VIEW  F2 camera (third / top-down / side / front / face / orbit)  wheel zoom  , . orbit  O skeleton overlay"),
		TEXT("SHOW  F3 face panel  F4 animation browser  F5 team A/B  F6 LOD (auto/0/1/2)  F7 1 or 10 operatives  F8 team outline+icon"),
		TEXT("      F9 deterministic showcase sequence (trace -> Saved/Logs/MorphRig_Trace.txt)  [ ] action rate 0.5-1.5  F1 hide help"),
	};
}

void AMorphHUD::Line(float X, float& Y, const FString& S, const FLinearColor& C, float Scale)
{
	UFont* F = GEngine->GetSmallFont();
	Canvas->SetDrawColor(C.ToFColor(true));
	Canvas->DrawText(F, S, X + 1.f, Y + 1.f, Scale, Scale);
	Y += 16.f * Scale;
}

void AMorphHUD::DrawTimeline(float X, float Y, float W)
{
	const AMorphPlayerController* PC = Cast<AMorphPlayerController>(PlayerOwner);
	const AMorphOperative* O = PC ? PC->Op() : nullptr;
	if (!O || !O->GetLibrary())
	{
		return;
	}
	const FString Id = O->CurrentClipName();
	const FMorphClip* C = O->GetLibrary()->Find(FName(*Id));
	const float Len = C ? FMath::Max(C->Duration, 0.01f) : 1.f;
	const float T = O->CurrentClipTime();
	const float U = C ? FMath::Clamp(T / Len, 0.f, 1.f) : T;
	FCanvasTileItem Bg(FVector2D(X, Y), FVector2D(W, 10.f), FLinearColor(0.1f, 0.1f, 0.12f, 0.8f));
	Bg.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Bg);
	FCanvasTileItem Fg(FVector2D(X, Y), FVector2D(W * U, 10.f), FLinearColor(0.1f, 0.75f, 0.95f, 0.9f));
	Fg.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Fg);
	if (C)
	{
		UFont* F = GEngine->GetTinyFont();
		for (int32 i = 0; i < C->Markers.Num(); ++i)
		{
			const float MX = X + W * FMath::Clamp(C->Markers[i].Time / Len, 0.f, 1.f);
			FCanvasTileItem Tick(FVector2D(MX - 1.f, Y - 4.f), FVector2D(2.f, 18.f), FLinearColor(1.f, 0.8f, 0.2f, 1.f));
			Canvas->DrawItem(Tick);
			Canvas->SetDrawColor(FColor(255, 210, 90));
			Canvas->DrawText(F, C->Markers[i].Name.ToString(), MX + 2.f, Y + 12.f + 10.f * (i % 3), 1.f, 1.f);
		}
		Canvas->SetDrawColor(FColor::White);
		Canvas->DrawText(GEngine->GetSmallFont(),
		                 FString::Printf(TEXT("%s  %.2f / %.2f s  frame %d / %d  %s"), *Id, T, Len,
		                                 FMath::RoundToInt(T * 30.f), C->Frames, C->bLoop ? TEXT("loop") : TEXT("one-shot")),
		                 X, Y - 18.f);
	}
}

void AMorphHUD::DrawHUD()
{
	Super::DrawHUD();
	const AMorphShowcaseGameMode* G = GetWorld()->GetAuthGameMode<AMorphShowcaseGameMode>();
	const AMorphPlayerController* PC = Cast<AMorphPlayerController>(PlayerOwner);
	const AMorphOperative* O = PC ? PC->Op() : nullptr;
	if (!O || !Canvas)
	{
		return;
	}
	if (G && G->IsCapturing() && PC->GetCameraMode() != EMorphCamera::ThirdPerson &&
	    PC->GetCameraMode() != EMorphCamera::Side && PC->GetCameraMode() != EMorphCamera::TopDown &&
	    PC->GetCameraMode() != EMorphCamera::Front)
	{
		return;     // clean face close-up / turntable frames
	}
	const float Dt = FApp::GetDeltaTime();
	SmoothMs = FMath::Lerp(SmoothMs, Dt * 1000.f, 0.05f);
	SmoothFps = SmoothMs > 0.f ? 1000.f / SmoothMs : 0.f;
	float Y = 12.f;
	const float X = 14.f;
	Line(X, Y, TEXT("MORPHRIG OPERATIVE SHOWCASE"), FLinearColor(0.2f, 0.85f, 1.f), 1.25f);
	Line(X, Y, FString::Printf(TEXT("state  %s   clip %s   speed %.0f cm/s   action rate %.1fx"), *O->StateName(),
	                           *O->CurrentClipName(), O->GetSpeedCms(), O->GetRateScale()));
	static const TCHAR* Stances[3] = {TEXT("relaxed"), TEXT("combat"), TEXT("wounded")};
	Line(X, Y, FString::Printf(TEXT("stance %s   strafe %s   team %s   LOD %s   camera %s   operatives %d"),
	                           Stances[int32(O->GetStance())], O->IsStrafe() ? TEXT("on") : TEXT("off"),
	                           O->GetTeam() == 0 ? TEXT("A (cyan / chevron)") : TEXT("B (orange / ring)"),
	                           O->GetForcedLOD() == 0 ? TEXT("auto") : *FString::FromInt(O->GetForcedLOD() - 1),
	                           *PC->CameraName(), G ? G->GetInstanceCount() : 1));
	Line(X, Y, O->DescribeLayers(), FLinearColor(0.6f, 0.7f, 0.75f));
	Line(X, Y, FString::Printf(TEXT("%.1f fps  %.2f ms   events %d"), SmoothFps, SmoothMs, O->GetEventCount()),
	     FLinearColor(0.6f, 0.9f, 0.6f));
	if (G && !G->SequenceStatus().IsEmpty())
	{
		Line(X, Y, G->SequenceStatus(), FLinearColor(1.f, 0.8f, 0.3f));
	}
	if (G && !G->BenchStatus().IsEmpty())
	{
		Line(X, Y, G->BenchStatus(), FLinearColor(1.f, 0.6f, 0.3f));
	}
	DrawTimeline(X, Y + 26.f, 520.f);
	// event log (right)
	float EY = 12.f;
	const float EX = Canvas->ClipX - 470.f;
	Line(EX, EY, TEXT("EVENTS / STATE TRACE"), FLinearColor(0.2f, 0.85f, 1.f));
	const TArray<FMorphEventLog>& Log = O->GetEventLog();
	for (int32 i = FMath::Max(0, Log.Num() - 14); i < Log.Num(); ++i)
	{
		const bool bEvent = Log[i].Text.StartsWith(TEXT("event"));
		Line(EX, EY, FString::Printf(TEXT("%7.2f  %s"), Log[i].GameTime, *Log[i].Text.Left(58)),
		     bEvent ? FLinearColor(1.f, 0.85f, 0.4f) : FLinearColor(0.8f, 0.85f, 0.9f), 0.9f);
	}
	if (PC->IsHelpVisible() && !(G && G->IsCapturing()))
	{
		float HY = Canvas->ClipY - 20.f - 15.f * UE_ARRAY_COUNT(HelpLines);
		for (const TCHAR* H : HelpLines)
		{
			Line(X, HY, H, FLinearColor(0.75f, 0.8f, 0.85f), 0.9f);
		}
	}
}
