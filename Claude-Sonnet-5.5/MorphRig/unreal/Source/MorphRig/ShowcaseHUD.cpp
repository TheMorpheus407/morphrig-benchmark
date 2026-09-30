#include "ShowcaseHUD.h"
#include "ShowcasePlayerController.h"
#include "ShowcaseDirector.h"
#include "ShowcaseRoom.h"
#include "OperativeActionComponent.h"
#include "OperativeFaceComponent.h"
#include "OperativeCharacter.h"
#include "OperativeLibrary.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Misc/App.h"

void AShowcaseHUD::Line(const FString& Text, float X, float Y, const FLinearColor& Color, float Scale)
{
	if (!Canvas) return;
	FCanvasTextItem Item(FVector2D(X, Y), FText::FromString(Text), GEngine->GetSmallFont(), Color);
	Item.Scale = FVector2D(S * Scale, S * Scale);
	Item.EnableShadow(FLinearColor(0.f, 0.f, 0.f, 0.9f));
	Canvas->DrawItem(Item);
}

void AShowcaseHUD::Rect(float X, float Y, float W, float H, const FLinearColor& Color)
{
	if (!Canvas) return;
	FCanvasTileItem Tile(FVector2D(X, Y), GWhiteTexture, FVector2D(W, H), Color);
	Tile.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Tile);
}

void AShowcaseHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas || HudLevel <= 0) return;
	S = FMath::Max(1.f, Canvas->ClipY / 1080.f);
	LineH = 14.f * S;
	AShowcasePlayerController* PC = Cast<AShowcasePlayerController>(GetOwningPlayerController());
	AOperativeCharacter* Op = PC ? PC->GetOperative() : nullptr;
	UOperativeActionComponent* A = Op ? Op->Actions.Get() : nullptr;
	if (!PC || !Op || !A) return;
	if (HudLevel >= 1 && !Caption.IsEmpty())
	{
		Rect(Canvas->ClipX * 0.5f - 260.f * S, 10.f * S, 520.f * S, 24.f * S, FLinearColor(0.f, 0.f, 0.f, 0.55f));
		Line(Caption, Canvas->ClipX * 0.5f - 250.f * S, 15.f * S, FLinearColor(0.6f, 0.95f, 1.f), 1.3f);
	}
	DrawSubtitle(A);
	if (HudLevel >= 2)
	{
		DrawState(PC, Op, A);
		if (PC->IsHelpVisible()) DrawHelp(PC);
	}
}

void AShowcaseHUD::DrawSubtitle(UOperativeActionComponent* A)
{
	// subtitles from dialogue_alignment.json: the sentence that is being spoken, the current word highlighted (audio starts with the clip)
	if (A->GetActionKind() != EOperativeAction::Dialogue || A->GetBaseClipId() != FName("dialogue")) return;
	const UOperativeLibrary* L = A->GetLibrary();
	if (!L) return;
	const TArray<FOperativeSpeechSpan>& Sentences = L->GetSpeechSentences();
	const TArray<FOperativeSpeechSpan>& Words = L->GetSpeechWords();
	const float T = A->GetBaseClipTime();
	int32 Current = INDEX_NONE;
	for (int32 I = 0; I < Sentences.Num(); ++I)
	{
		if (T >= Sentences[I].Start - 0.08f && T <= Sentences[I].End + 0.45f) Current = I;
	}
	if (Current == INDEX_NONE) return;
	UFont* Font = GEngine->GetSmallFont();
	const float Scale = 1.9f * S;
	TArray<FString> Parts;
	TArray<bool> Highlight;
	TArray<float> Widths;
	float Total = 0.f, TextH = 0.f;
	for (const FOperativeSpeechSpan& W : Words)
	{
		if (W.Sentence != Current) continue;
		const FString Piece = W.Text + TEXT(" ");
		float XL = 0.f, YL = 0.f;
		Canvas->StrLen(Font, Piece, XL, YL);
		Parts.Add(Piece);
		Highlight.Add(T >= W.Start - 0.02f && T < W.End + 0.02f);
		Widths.Add(XL * Scale);
		Total += XL * Scale;
		TextH = FMath::Max(TextH, YL * Scale);
	}
	if (Parts.Num() == 0)
	{
		float XL = 0.f, YL = 0.f;
		Canvas->StrLen(Font, Sentences[Current].Text, XL, YL);
		Parts.Add(Sentences[Current].Text);
		Highlight.Add(false);
		Widths.Add(XL * Scale);
		Total = XL * Scale;
		TextH = YL * Scale;
	}
	const float Y = Canvas->ClipY - 120.f * S;
	float X = (Canvas->ClipX - Total) * 0.5f;
	Rect(X - 24.f * S, Y - 10.f * S, Total + 48.f * S, TextH + 20.f * S, FLinearColor(0.f, 0.f, 0.f, 0.6f));
	for (int32 I = 0; I < Parts.Num(); ++I)
	{
		Line(Parts[I], X, Y, Highlight[I] ? FLinearColor(1.f, 0.88f, 0.35f) : FLinearColor(0.95f, 0.97f, 1.f), 1.9f);
		X += Widths[I];
	}
}

void AShowcaseHUD::DrawState(AShowcasePlayerController* PC, AOperativeCharacter* Op, UOperativeActionComponent* A)
{
	const float X0 = (PC->IsPanelVisible() ? 386.f : 12.f) * S;
	float Y = 10.f * S;
	const float W = 560.f * S;
	Rect(X0 - 6.f * S, Y - 4.f * S, W, 250.f * S, FLinearColor(0.f, 0.f, 0.02f, 0.62f));
	const FLinearColor White(1.f, 1.f, 1.f), Cyan(0.5f, 0.9f, 1.f), Yellow(1.f, 0.9f, 0.5f), Grey(0.7f, 0.75f, 0.8f), Green(0.5f, 1.f, 0.6f);
	const FVector Vel = Op->GetVelocity();
	const float Speed = FVector(Vel.X, Vel.Y, 0.f).Size();
	Line(FString::Printf(TEXT("STATE   %s    priority %d    stance %s    health %d%%"), *A->GetStateString(), A->GetCurrentPriority(),
		A->GetStance() == EOperativeStance::Relaxed ? TEXT("relaxed") : A->GetStance() == EOperativeStance::Combat ? TEXT("combat") : TEXT("wounded"), FMath::RoundToInt(A->GetHealthFraction() * 100.f)), X0, Y, White);
	Y += LineH;
	const FOperativePlayer& B = A->GetBasePlayer();
	Line(FString::Printf(TEXT("CLIP    %s   %.2f / %.2f s   rate %.2f   action rate %.2f%s"), *B.ClipId.ToString(), B.Time, B.Length, B.Rate, A->GetActionRate(),
		A->GetUpperClipId().IsNone() ? TEXT("") : *FString::Printf(TEXT("   upper %s %.2f"), *A->GetUpperClipId().ToString(), A->GetUpperPlayer().Time)), X0, Y, Yellow);
	Y += LineH;
	const float Theta = A->GetState() == EOperativeState::Locomotion ? 0.f : 0.f;
	Line(FString::Printf(TEXT("MOVE    speed %.0f cm/s   loco phase %.2f   facing %s   %s"), Speed, A->GetLocomotionPhase(), *PC->GetFacingModeName(),
		Op->GetCharacterMovement()->IsMovingOnGround() ? TEXT("grounded") : TEXT("airborne")), X0, Y, Cyan);
	Y += LineH;
	Line(FString::Printf(TEXT("AIM     yaw %+.1f (left +)   pitch %+.1f (up +)   %s   shots %d   blade hits %d   target hits %d"), A->GetAimYaw(), A->GetAimPitch(),
		A->IsAiming() ? TEXT("aim layer on") : TEXT("aim layer off"), Op->GetShotsFired(), Op->GetBladeHits(), PC->GetRoom() ? PC->GetRoom()->TotalTargetHits() : 0), X0, Y, Cyan);
	Y += LineH;
	FString Flags;
	if (A->IsRooted()) Flags += TEXT("ROOT ");
	if (A->IsSilenced()) Flags += TEXT("SILENCE ");
	if (A->IsDisarmed()) Flags += TEXT("DISARM ");
	if (A->IsStasis()) Flags += TEXT("STASIS ");
	if (A->IsChannelSustained()) Flags += TEXT("CHANNEL ");
	if (A->IsChargeHolding()) Flags += FString::Printf(TEXT("CHARGE %.0f%% "), A->GetChargeFraction() * 100.f);
	if (A->IsMeleeWindowOpen()) Flags += TEXT("HIT-WINDOW ");
	if (Op->IsBeaconDeployed()) Flags += TEXT("BEACON ");
	Line(FString::Printf(TEXT("VIEW    %s   render %s   LOD %s   team %s   instances %d   %s"), *PC->GetViewName(), *PC->GetRenderModeName(),
		Op->GetForcedLOD() == 0 ? TEXT("auto") : *FString::FromInt(Op->GetForcedLOD() - 1), Op->GetTeam() == EOperativeTeam::A ? TEXT("A cyan circle") : TEXT("B magenta diamond"), PC->GetInstanceCount(), *Flags), X0, Y, Grey);
	Y += LineH;
	if (AShowcaseDirector* D = PC->GetDirector())
	{
		if (D->IsSequenceRunning() || D->IsCapturing())
		{
			Line(FString::Printf(TEXT("SEQUENCE %s   %s"), *D->GetSequenceStatus(), *D->GetCaptureModeName()), X0, Y, Green);
			Y += LineH;
		}
	}
	Line(FString::Printf(TEXT("FPS %.0f   character %.0f px tall on screen   duplicate events %d   events %d"), 1.f / FMath::Max(FApp::GetDeltaTime(), 1e-4), PC->GetCharacterPixelHeight(), A->GetDuplicateEventCount(), A->GetEventCount()), X0, Y, Grey);
	Y += LineH * 1.4f;
	DrawTimeline(A, X0, Y, W - 30.f * S);
	Y += LineH * 4.2f;
	Line(TEXT("EVENTS (newest last)"), X0, Y, Cyan);
	Y += LineH;
	const TArray<FOperativeEventInfo>& Ev = A->GetRecentEvents();
	const int32 Start = FMath::Max(0, Ev.Num() - 8);
	for (int32 I = Start; I < Ev.Num(); ++I)
	{
		const FOperativeEventInfo& E = Ev[I];
		Line(FString::Printf(TEXT("%7.2f  %-22s %-16s t=%.2f %s%s"), E.WorldTime, *E.Name.ToString(), *E.ClipId.ToString(), E.ClipTime, *E.Params, E.bSynthetic ? TEXT("  (fallback)") : TEXT("")), X0, Y, E.bSynthetic ? Yellow : Green, 0.95f);
		Y += LineH;
	}
}

void AShowcaseHUD::DrawTimeline(UOperativeActionComponent* A, float X, float Y, float W)
{
	// marker timeline of the playing clip: events as ticks (green = manifest, yellow = runtime fallback), playhead in white
	const FOperativePlayer& P = A->GetBasePlayer();
	if (!P.bActive || P.Length <= 0.f) return;
	const float H = 12.f * S;
	Rect(X, Y, W, H, FLinearColor(0.1f, 0.12f, 0.16f, 0.9f));
	if (P.Events)
	{
		int32 Row = 0;
		for (const FOperativeEventDef& E : *P.Events)
		{
			const float U = FMath::Clamp(E.TimeS / P.Length, 0.f, 1.f);
			const FLinearColor Col = E.bSynthetic ? FLinearColor(1.f, 0.85f, 0.3f) : FLinearColor(0.4f, 1.f, 0.5f);
			Rect(X + U * W - 1.f * S, Y - 3.f * S, 2.f * S, H + 6.f * S, Col);
			Line(E.Name.ToString(), X + U * W + 2.f * S, Y + H + (Row % 3) * LineH * 0.8f, Col, 0.72f);
			++Row;
		}
	}
	const float U = FMath::Clamp(P.Time / P.Length, 0.f, 1.f);
	Rect(X + U * W - 2.f * S, Y - 5.f * S, 4.f * S, H + 10.f * S, FLinearColor::White);
	if (A->GetUpperPlayer().bActive)
	{
		const FOperativePlayer& Up = A->GetUpperPlayer();
		const float Y2 = Y + H + 3.f * LineH;
		Rect(X, Y2, W, 8.f * S, FLinearColor(0.12f, 0.1f, 0.16f, 0.9f));
		const float U2 = FMath::Clamp(Up.Time / FMath::Max(Up.Length, 1e-3f), 0.f, 1.f);
		Rect(X + U2 * W - 2.f * S, Y2 - 3.f * S, 4.f * S, 14.f * S, FLinearColor(1.f, 0.6f, 0.9f));
	}
}

void AShowcaseHUD::DrawHelp(AShowcasePlayerController* PC)
{
	const float X0 = Canvas->ClipX * 0.5f - 470.f * S;
	float Y = Canvas->ClipY * 0.5f - 400.f * S;
	Rect(X0 - 12.f * S, Y - 10.f * S, 940.f * S, 800.f * S, FLinearColor(0.f, 0.02f, 0.04f, 0.9f));
	Line(TEXT("CONTROLS  (F1 closes; the panel on the left offers every function with the mouse)"), X0, Y, FLinearColor(0.5f, 0.95f, 1.f), 1.3f);
	Y += LineH * 1.8f;
	FString LastCat;
	for (const FShowcaseBinding& B : PC->GetBindings())
	{
		if (B.Category != LastCat)
		{
			LastCat = B.Category;
			Y += LineH * 0.5f;
			Line(FString::Printf(TEXT("[%s]"), *LastCat), X0, Y, FLinearColor(1.f, 0.85f, 0.4f));
			Y += LineH;
		}
		Line(B.KeyText, X0 + 10.f * S, Y, FLinearColor(0.6f, 1.f, 0.7f));
		Line(B.Description, X0 + 210.f * S, Y, FLinearColor(0.85f, 0.88f, 0.92f));
		Y += LineH;
	}
	Line(TEXT("Command line: -ShowcaseSequence  -CaptureMode=turntable|motion|face -CaptureDir=DIR  -PerfLog=FILE.csv  -Instances=1|10  -NoPanel"), X0, Y + LineH, FLinearColor(0.7f, 0.7f, 0.8f));
}
