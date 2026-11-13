#include "ShowcaseHUD.h"
#include "MorphRig.h"
#include "MorphRigData.h"
#include "OperativeCharacter.h"
#include "OperativeStateComponent.h"
#include "ShowcaseDirector.h"
#include "ShowcasePlayerController.h"
#include "Animation/AnimSequence.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/SkeletalMesh.h"
#include "Misc/App.h"

namespace
{
	const FLinearColor ColTitle(0.55f, 0.85f, 1.0f), ColDim(0.72f, 0.74f, 0.78f), ColWarn(1.0f, 0.72f, 0.2f), ColGood(0.5f, 1.0f, 0.6f), ColEvent(1.0f, 0.9f, 0.45f);
	const float LineH = 19.f;
}

void AShowcaseHUD::Line(const FString& Text, const FLinearColor& Color, float Scale)
{
	UFont* Font = GEngine->GetMediumFont();
	const float S = Scale * 1.12f;
	DrawText(Text, FLinearColor(0, 0, 0, 0.85f), CursorX + 1.f, CursorY + 1.f, Font, S);
	DrawText(Text, Color, CursorX, CursorY, Font, S);
	CursorY += LineH * Scale;
}

void AShowcaseHUD::DrawClipBar(const FOpClipPlay& Play, const TCHAR* Label, const FLinearColor& Color)
{
	if (!Play.IsValid())
	{
		Line(FString::Printf(TEXT("%s: -"), Label), ColDim);
		return;
	}
	const float Dur = FMath::Max(Play.Duration(), 1.e-3f);
	const FMorphRigData& Data = FMorphRigData::Get();
	Line(FString::Printf(TEXT("%s: %-18s t=%.3f / %.3f s   frame %5.1f / %d   #%d%s"), Label, *Play.Id().ToString(), Play.Time, Dur,
		Play.Time * Data.Fps, Play.Info->FrameEnd, Play.ActivationId, Play.bLoop ? TEXT("  loop") : TEXT("")), Color);
	const float W = 500.f, H = 9.f;
	DrawRect(FLinearColor(0.02f, 0.02f, 0.03f, 0.75f), CursorX, CursorY + 2.f, W, H);
	DrawRect(Color * FLinearColor(1, 1, 1, 0.85f), CursorX, CursorY + 2.f, W * FMath::Clamp(Play.Time / Dur, 0.f, 1.f), H);
	UFont* Small = GEngine->GetSmallFont();
	int32 Row = 0;
	float LastX = -1000.f;
	for (const FMorphEvent& E : Play.Info->Events)
	{
		const float X = CursorX + W * FMath::Clamp(E.Time / Dur, 0.f, 1.f);
		const bool bPassed = E.Time <= Play.Time;
		DrawRect(bPassed ? ColEvent : FLinearColor(0.9f, 0.9f, 0.9f, 0.9f), X - 1.f, CursorY, 2.f, H + 4.f);
		Row = (X - LastX < 78.f) ? (Row + 1) % 3 : 0;
		LastX = X;
		DrawText(E.Name.ToString(), bPassed ? ColEvent : ColDim, X + 3.f, CursorY + H + 4.f + Row * 11.f, Small, 1.f);
	}
	CursorY += H + 8.f + (Play.Info->Events.Num() > 0 ? 34.f : 0.f);
}

void AShowcaseHUD::DrawSkeleton(AOperativeCharacter* Ch)
{
	USkeletalMeshComponent* Mesh = Ch->GetMesh();
	USkeletalMesh* SK = Mesh->GetSkeletalMeshAsset();
	if (!SK)
	{
		return;
	}
	const FReferenceSkeleton& Ref = SK->GetRefSkeleton();
	const TArray<FTransform>& CS = Mesh->GetComponentSpaceTransforms();
	const FTransform C2W = Mesh->GetComponentTransform();
	if (CS.Num() != Ref.GetNum())
	{
		return;
	}
	TArray<FVector2D> P;
	TArray<bool> bOk;
	P.SetNum(CS.Num());
	bOk.SetNum(CS.Num());
	for (int32 i = 0; i < CS.Num(); ++i)
	{
		const FVector S = Project(C2W.TransformPosition(CS[i].GetLocation()));
		P[i] = FVector2D(S.X, S.Y);
		bOk[i] = S.Z > 0.0;
	}
	for (int32 i = 1; i < CS.Num(); ++i)
	{
		const int32 Parent = Ref.GetParentIndex(i);
		if (Parent < 0 || !bOk[i] || !bOk[Parent])
		{
			continue;
		}
		const FString Name = Ref.GetBoneName(i).ToString();
		FLinearColor Col(0.2f, 1.0f, 0.5f);
		if (Name.Contains(TEXT("twist")) || Name.Contains(TEXT("helper")))
		{
			Col = FLinearColor(1.0f, 0.55f, 0.1f);
		}
		else if (Name.StartsWith(TEXT("prop_")) || Name.StartsWith(TEXT("blade")) || Name.StartsWith(TEXT("cable")))
		{
			Col = FLinearColor(1.0f, 0.3f, 0.8f);
		}
		DrawLine((float)P[Parent].X, (float)P[Parent].Y, (float)P[i].X, (float)P[i].Y, Col, 1.5f);
		DrawRect(Col, (float)P[i].X - 1.5f, (float)P[i].Y - 1.5f, 3.f, 3.f);
	}
}

void AShowcaseHUD::DrawHUD()
{
	Super::DrawHUD();
	AShowcaseDirector* D = AShowcaseDirector::Get(this);
	if (!D || !Canvas)
	{
		return;
	}
	const FMorphRigData& Data = FMorphRigData::Get();
	AOperativeCharacter* Ch = D->GetPrimary();
	const float SW = (float)Canvas->SizeX, SH = (float)Canvas->SizeY;
	UFont* Font = GEngine->GetMediumFont();

	// ---- world space: skeleton overlay and floating state labels
	for (AOperativeCharacter* Inst : D->GetInstances())
	{
		if (!Inst)
		{
			continue;
		}
		if (D->bShowSkeleton)
		{
			DrawSkeleton(Inst);
		}
		const FString Flags = Inst->StateComp->GetFlagsText();
		const EOpState St = Inst->StateComp->GetState();
		FString Label = Flags;
		if (St == EOpState::Stun || St == EOpState::Sleep || St == EOpState::Dead || St == EOpState::Knockdown || St == EOpState::Knockup)
		{
			Label = (Flags.IsEmpty() ? FString() : Flags + TEXT(" ")) + Inst->StateComp->GetStateText().ToUpper();
		}
		if (!Label.IsEmpty())
		{
			const FVector S = Project(Inst->GetActorLocation() + FVector(0, 0, 118));
			if (S.Z > 0.0)
			{
				float TW = 0.f, TH = 0.f;
				GetTextSize(Label, TW, TH, Font, 1.f);
				DrawRect(FLinearColor(0, 0, 0, 0.55f), (float)S.X - TW * 0.5f - 5.f, (float)S.Y - TH - 3.f, TW + 10.f, TH + 6.f);
				DrawText(Label, ColWarn, (float)S.X - TW * 0.5f, (float)S.Y - TH, Font, 1.f);
			}
		}
	}
	if (!Ch)
	{
		return;
	}
	UOperativeStateComponent* S = Ch->StateComp;
	// ---- caption (sequence chapter / presentation label)
	if (D->CaptionTime > 0.f && !D->Caption.IsEmpty())
	{
		float TW = 0.f, TH = 0.f;
		GetTextSize(D->Caption, TW, TH, Font, 2.f);
		const float Alpha = FMath::Clamp(D->CaptionTime * 2.f, 0.f, 1.f);
		DrawRect(FLinearColor(0, 0, 0, 0.6f * Alpha), SW * 0.5f - TW * 0.5f - 16.f, SH - 158.f, TW + 32.f, TH + 16.f);
		DrawText(D->Caption, FLinearColor(1, 1, 1, Alpha), SW * 0.5f - TW * 0.5f, SH - 150.f, Font, 2.f);
	}
	// ---- subtitles for the speech sample
	{
		const FOpClipPlay& Base = S->GetBaseClip();
		if (Base.IsValid() && Base.Id() == FName(TEXT("dialogue")) && Data.Dialogue.Words.Num() > 0)
		{
			const float T = Base.Time - Data.Dialogue.AudioStartTime;
			FString Sentence, Current, Viseme;
			for (const FMorphWord& W : Data.Dialogue.Words)
			{
				const bool bNow = T >= W.Start && T <= W.End;
				Sentence += (bNow ? FString::Printf(TEXT("[%s] "), *W.Text) : W.Text + TEXT(" "));
			}
			for (const FMorphWord& Ph : Data.Dialogue.Phonemes)
			{
				if (T >= Ph.Start && T <= Ph.End)
				{
					Current = Ph.Text;
					Viseme = Ph.Viseme;
				}
			}
			float TW = 0.f, TH = 0.f;
			GetTextSize(Sentence, TW, TH, Font, 1.25f);
			const float X = FMath::Max(20.f, SW * 0.5f - TW * 0.5f);
			DrawRect(FLinearColor(0, 0, 0, 0.6f), X - 10.f, SH - 92.f, FMath::Min(TW + 20.f, SW - 40.f), TH + 34.f);
			DrawText(Sentence, FLinearColor::White, X, SH - 88.f, Font, 1.25f);
			DrawText(FString::Printf(TEXT("clip t=%.2f s   audio t=%.2f s   phoneme %s   viseme %s   audio %s"), Base.Time, T, *Current, *Viseme,
				Ch->IsDialogueAudioPlaying() ? TEXT("playing") : TEXT("stopped")), ColDim, X, SH - 88.f + TH + 4.f, Font, 1.f);
		}
	}
	if (!D->bShowHud)
	{
		return;
	}

	// ---- left column: state / clips / locomotion
	CursorX = 22.f;
	CursorY = 18.f;
	DrawRect(FLinearColor(0.0f, 0.0f, 0.0f, 0.5f), 10.f, 10.f, 560.f, 560.f);
	Line(FString::Printf(TEXT("MORPHRIG Operative showcase%s"), Data.bPlaceholder ? TEXT("   [PLACEHOLDER ASSETS]") : TEXT("")), ColTitle, 1.1f);
	if (!Data.bValid)
	{
		Line(FString::Printf(TEXT("DATA ERROR: %s"), *Data.Error), FLinearColor::Red);
	}
	if (Data.DisabledMorphs.Num() > 0)
	{
		Line(FString::Printf(TEXT("%d of %d morph targets failed the import check and are disabled"), Data.DisabledMorphs.Num(), Data.Morphs.Num()), FLinearColor(1.f, 0.55f, 0.2f));
	}
	const FString Flags = S->GetFlagsText();
	Line(FString::Printf(TEXT("State: %s    %s"), *S->GetStateText(), Flags.IsEmpty() ? TEXT("") : *FString::Printf(TEXT("[%s]"), *Flags)), ColGood, 1.1f);
	DrawClipBar(S->GetBaseClip(), TEXT("Base "), FLinearColor(0.35f, 0.75f, 1.0f));
	DrawClipBar(S->GetUpperClip(), TEXT("Upper"), FLinearColor(1.0f, 0.6f, 0.3f));
	Line(FString::Printf(TEXT("Speed %5.0f cm/s   dir %+5.0f deg   gait phase %.2f   gait rate %.2fx   %s"), S->GetSpeed(), S->GetTravelDirDeg(),
		S->GetGaitPhase(), S->GetLocoRate(), S->bStrafe ? TEXT("strafe") : TEXT("travel")), FLinearColor::White);
	if (S->GetState() == EOpState::Locomotion && !S->GetBaseClip().IsValid())
	{
		Line(FString::Printf(TEXT("Blend: %s"), *S->GetLocoText()), ColDim);
	}
	Line(FString::Printf(TEXT("Aim yaw %+5.1f  pitch %+5.1f  weight %.2f   %s"), S->GetAimYaw(), S->GetAimPitch(), S->GetAimAlpha(),
		D->LockedTarget != INDEX_NONE ? *FString::Printf(TEXT("locked target %d"), D->LockedTarget) : TEXT("free aim")), FLinearColor::White);
	Line(FString::Printf(TEXT("Ground IK %s: foot L %+5.1f  R %+5.1f  pelvis %+5.1f cm   ankle above surface L %4.1f  R %4.1f cm"), S->bFootIK ? TEXT("on") : TEXT("off"),
		S->GetFootOffset(0), S->GetFootOffset(1), S->GetPelvisOffset(), S->GetFootClearance(0), S->GetFootClearance(1)), ColDim);
	Line(FString::Printf(TEXT("Ammo %d   charge %.2f   beacon %s   expression %s   action rate %.2fx"), S->GetAmmo(), S->GetChargeLevel(),
		S->IsBeaconCarried() ? TEXT("on belt") : TEXT("deployed"), *S->GetAutoExpression(), S->ActionRate), ColDim);
	FName Prop, Holder;
	const float Contact = Ch->GetContactError(Prop, Holder);
	if (Contact >= 0.f)
	{
		Line(FString::Printf(TEXT("Contact: %s held by %s   socket distance %.2f cm"), *Prop.ToString(), *Holder.ToString(), Contact), ColGood);
	}
	{
		// prop contact read-out while a manipulation clip plays (distances between hand sockets and prop bones)
		const FName BaseId = S->GetBaseClip().Id(), UpperId = S->GetUpperClip().Id();
		static const FName NAME_Reload(TEXT("reload")), NAME_Deploy(TEXT("deploy"));
		if (BaseId == NAME_Deploy || UpperId == NAME_Reload || BaseId == NAME_Reload || BaseId.ToString().StartsWith(TEXT("uplink")))
		{
			USkeletalMeshComponent* M = Ch->GetMesh();
			const FVector HL = M->GetSocketLocation(TEXT("hand_l_socket")), HR = M->GetSocketLocation(TEXT("hand_r_socket"));
			auto Dist = [&](const FVector& A, const TCHAR* Bone) { return (float)FVector::Dist(A, M->GetSocketLocation(Bone)); };
			Line(FString::Printf(TEXT("Hands to props (cm): L-cell %.1f  L-spare %.1f  L-slot %.1f  R-beacon %.1f  L-beacon %.1f"),
				Dist(HL, TEXT("prop_cell")), Dist(HL, TEXT("prop_cell_spare")), Dist(HL, TEXT("cell_slot")), Dist(HR, TEXT("prop_beacon")), Dist(HL, TEXT("prop_beacon"))), ColGood);
		}
	}
	static const TCHAR* DisplayNames[4] = { TEXT("textured"), TEXT("wireframe"), TEXT("normals"), TEXT("clay") };
	Line(FString::Printf(TEXT("Team %s%s%s   LOD %s (showing %d)   %s   camera: %s"), Ch->GetTeam() ? TEXT("B") : TEXT("A"), Ch->HasOutline() ? TEXT(" +outline") : TEXT(""),
		Ch->HasRing() ? TEXT(" +ring") : TEXT(""), Ch->GetLodMode() == 0 ? TEXT("auto") : *FString::FromInt(Ch->GetLodMode() - 1), Ch->GetCurrentLod(),
		DisplayNames[(int32)Ch->GetDisplayMode()], *D->GetCameraName()), ColDim);
	const float Ms = FApp::GetDeltaTime() * 1000.f;
	FrameMsSmoothed = FMath::Lerp(FrameMsSmoothed, Ms, 0.08f);
	Line(FString::Printf(TEXT("Instances %d   frame %.2f ms (%.0f fps)   body height on screen %.0f px   t=%.2f s"), D->GetInstances().Num(),
		FrameMsSmoothed, FrameMsSmoothed > 0.f ? 1000.f / FrameMsSmoothed : 0.f, D->GetProjectedBodyHeightPx(), D->GetShowcaseTime()), ColDim);

	// ---- event log
	CursorY += 4.f;
	Line(FString::Printf(TEXT("Events (%d dispatched)"), S->GetEventCount()), ColTitle);
	const TArray<FOpEventRecord>& Log = S->GetEventLog();
	for (int32 i = FMath::Max(0, Log.Num() - 9); i < Log.Num(); ++i)
	{
		const FOpEventRecord& R = Log[i];
		const float Age = (float)(S->GetStateTime() - R.WorldTime);
		Line(FString::Printf(TEXT("%8.3f  %-17s %-18s @%.3f  #%d"), R.WorldTime, *R.Event.ToString(), *R.Clip.ToString(), R.ClipTime, R.ActivationId),
			Age < 0.6f ? ColEvent : ColDim);
	}

	// ---- recent trace (commands, refusals, state changes)
	CursorX = 22.f;
	CursorY = SH - 20.f - LineH * 7.f;
	const TArray<FString>& Recent = D->GetRecentTrace();
	for (int32 i = FMath::Max(0, Recent.Num() - 6); i < Recent.Num(); ++i)
	{
		const bool bRefused = Recent[i].StartsWith(TEXT("REFUSED"));
		Line(Recent[i].Left(110), bRefused ? ColWarn : ColDim);
	}

	// ---- top centre: script / capture / benchmark status
	FString Status = D->GetScriptStatus();
	if (D->IsCapturing())
	{
		Status += FString::Printf(TEXT("%sCAPTURE frame %d"), Status.IsEmpty() ? TEXT("") : TEXT("   |   "), D->GetCaptureFrame());
	}
	if (D->IsBenchmarking())
	{
		Status += (Status.IsEmpty() ? TEXT("") : TEXT("   |   ")) + D->GetBenchStatus();
	}
	if (!Status.IsEmpty())
	{
		float TW = 0.f, TH = 0.f;
		GetTextSize(Status, TW, TH, Font, 1.f);
		DrawRect(FLinearColor(0, 0, 0, 0.5f), SW * 0.5f - TW * 0.5f - 8.f, 10.f, TW + 16.f, TH + 8.f);
		DrawText(Status, ColWarn, SW * 0.5f - TW * 0.5f, 14.f, Font, 1.f);
	}

	// ---- help overlay
	if (D->bShowHelp)
	{
		const FString Help = AShowcasePlayerController::HelpText();
		TArray<FString> Lines;
		Help.ParseIntoArrayLines(Lines);
		const float BoxW = 1010.f, BoxH = LineH * (Lines.Num() + 2);
		const float X = SW * 0.5f - BoxW * 0.5f, Y = SH * 0.5f - BoxH * 0.5f;
		DrawRect(FLinearColor(0, 0, 0, 0.8f), X, Y, BoxW, BoxH);
		CursorX = X + 14.f;
		CursorY = Y + 10.f;
		Line(TEXT("Controls (F1 closes)"), ColTitle, 1.1f);
		for (const FString& L : Lines)
		{
			Line(L, FLinearColor::White);
		}
	}
	else
	{
		DrawText(TEXT("F1 controls   F2 panel   F11 deterministic sequence   ~ console: mr <command>"), ColDim, SW * 0.5f - 250.f, SH - 22.f, Font, 1.f);
	}
}
