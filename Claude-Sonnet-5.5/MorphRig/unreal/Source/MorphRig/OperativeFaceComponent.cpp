#include "OperativeFaceComponent.h"
#include "OperativeLibrary.h"

namespace
{
	struct FPresetMorph
	{
		const TCHAR* Name;
		float Value;
	};

	struct FFacePreset
	{
		const TCHAR* Name;
		float Jaw;
		float Tongue;
		TArray<FPresetMorph> Morphs;
	};

	const TArray<FFacePreset>& FacePresetTable()
	{
		static const TArray<FFacePreset> Table = {
			{ TEXT("neutral"), 0.f, 0.f, {} },
			{ TEXT("joy_confidence"), 0.10f, 0.f, {
				{ TEXT("mouth_smile_l"), 0.85f }, { TEXT("mouth_smile_r"), 0.85f }, { TEXT("cheek_raise_l"), 0.6f }, { TEXT("cheek_raise_r"), 0.6f },
				{ TEXT("squint_l"), 0.25f }, { TEXT("squint_r"), 0.25f }, { TEXT("brow_up_out_l"), 0.25f }, { TEXT("brow_up_out_r"), 0.25f },
				{ TEXT("dimple_l"), 0.35f }, { TEXT("dimple_r"), 0.35f }, { TEXT("mouth_wide"), 0.2f } } },
			{ TEXT("anger"), 0.05f, 0.f, {
				{ TEXT("brow_down_l"), 0.95f }, { TEXT("brow_down_r"), 0.95f }, { TEXT("brow_pinch"), 0.7f }, { TEXT("squint_l"), 0.45f }, { TEXT("squint_r"), 0.45f },
				{ TEXT("nose_wrinkle_l"), 0.55f }, { TEXT("nose_wrinkle_r"), 0.55f }, { TEXT("nostril_flare_l"), 0.6f }, { TEXT("nostril_flare_r"), 0.6f },
				{ TEXT("lip_up_l"), 0.35f }, { TEXT("lip_up_r"), 0.35f }, { TEXT("lip_press"), 0.3f }, { TEXT("mouth_frown_l"), 0.35f }, { TEXT("mouth_frown_r"), 0.35f } } },
			{ TEXT("concern_sadness"), 0.f, 0.f, {
				{ TEXT("brow_up_in_l"), 0.9f }, { TEXT("brow_up_in_r"), 0.9f }, { TEXT("brow_pinch"), 0.25f }, { TEXT("mouth_frown_l"), 0.6f }, { TEXT("mouth_frown_r"), 0.6f },
				{ TEXT("lip_corner_down_l"), 0.6f }, { TEXT("lip_corner_down_r"), 0.6f }, { TEXT("chin_raise"), 0.45f }, { TEXT("squint_l"), 0.1f }, { TEXT("squint_r"), 0.1f } } },
			{ TEXT("surprise"), 0.55f, 0.f, {
				{ TEXT("brow_up_in_l"), 1.f }, { TEXT("brow_up_in_r"), 1.f }, { TEXT("brow_up_out_l"), 1.f }, { TEXT("brow_up_out_r"), 1.f },
				{ TEXT("eye_wide_l"), 1.f }, { TEXT("eye_wide_r"), 1.f }, { TEXT("mouth_funnel"), 0.3f }, { TEXT("nostril_flare_l"), 0.3f }, { TEXT("nostril_flare_r"), 0.3f } } },
			{ TEXT("pain"), 0.3f, 0.f, {
				{ TEXT("brow_up_in_l"), 0.8f }, { TEXT("brow_up_in_r"), 0.8f }, { TEXT("brow_pinch"), 0.85f }, { TEXT("squint_l"), 0.95f }, { TEXT("squint_r"), 0.95f },
				{ TEXT("cheek_raise_l"), 0.5f }, { TEXT("cheek_raise_r"), 0.5f }, { TEXT("nose_wrinkle_l"), 0.55f }, { TEXT("nose_wrinkle_r"), 0.55f },
				{ TEXT("mouth_wide"), 0.55f }, { TEXT("lip_up_l"), 0.45f }, { TEXT("lip_up_r"), 0.45f }, { TEXT("mouth_frown_l"), 0.4f }, { TEXT("mouth_frown_r"), 0.4f } } },
			{ TEXT("focus"), 0.f, 0.f, {
				{ TEXT("brow_down_l"), 0.4f }, { TEXT("brow_down_r"), 0.4f }, { TEXT("brow_pinch"), 0.3f }, { TEXT("squint_l"), 0.3f }, { TEXT("squint_r"), 0.3f },
				{ TEXT("lip_press"), 0.2f }, { TEXT("mouth_narrow"), 0.15f } } },
		};
		return Table;
	}
}

UOperativeFaceComponent::UOperativeFaceComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
	Random.Initialize(4711);
}

const TArray<FName>& UOperativeFaceComponent::GetPresetNames()
{
	static TArray<FName> Names;
	if (Names.Num() == 0)
	{
		for (const FFacePreset& P : FacePresetTable()) Names.Add(FName(P.Name));
	}
	return Names;
}

void UOperativeFaceComponent::CacheLibrary()
{
	if (bLibraryCached) return;
	UOperativeLibrary* Lib = UOperativeLibrary::Get(this);
	if (!Lib || !Lib->IsReady()) return;
	Library = Lib;
	MorphNames = Lib->GetMorphNames();
	MorphTarget.Init(0.f, MorphNames.Num());
	MorphCurrent.Init(0.f, MorphNames.Num());
	VisemeNames.Reset();
	for (const FOperativeViseme& V : Lib->GetVisemes()) VisemeNames.Add(V.Name);
	VisemeTarget.Init(0.f, VisemeNames.Num());
	VisemeCurrent.Init(0.f, VisemeNames.Num());
	State.MorphCount = MorphNames.Num();
	bLibraryCached = true;
}

void UOperativeFaceComponent::BeginPlay()
{
	Super::BeginPlay();
	CacheLibrary();
	// distinct blink rhythm per actor, deterministic for a given spawn order
	Random.Initialize(GetOwner() ? (int32)GetTypeHash(GetOwner()->GetFName()) : 4711);
	AutoBlinkTimer = Random.FRandRange(1.5f, 4.f);
}

void UOperativeFaceComponent::SetMorph(FName Name, float Value)
{
	CacheLibrary();
	const int32 I = MorphNames.IndexOfByKey(Name);
	if (I != INDEX_NONE) { MorphTarget[I] = FMath::Clamp(Value, 0.f, 1.f); ActivePreset = NAME_None; }
}

float UOperativeFaceComponent::GetMorph(FName Name) const
{
	const int32 I = MorphNames.IndexOfByKey(Name);
	return I != INDEX_NONE ? MorphTarget[I] : 0.f;
}

void UOperativeFaceComponent::SetViseme(FName Name, float Value)
{
	CacheLibrary();
	const int32 I = VisemeNames.IndexOfByKey(Name);
	if (I != INDEX_NONE) VisemeTarget[I] = FMath::Clamp(Value, 0.f, 1.f);
}

float UOperativeFaceComponent::GetViseme(FName Name) const
{
	const int32 I = VisemeNames.IndexOfByKey(Name);
	return I != INDEX_NONE ? VisemeTarget[I] : 0.f;
}

bool UOperativeFaceComponent::ApplyPreset(FName Preset)
{
	CacheLibrary();
	for (const FFacePreset& P : FacePresetTable())
	{
		if (FName(P.Name) != Preset) continue;
		for (float& V : MorphTarget) V = 0.f;
		for (const FPresetMorph& M : P.Morphs)
		{
			const int32 I = MorphNames.IndexOfByKey(FName(M.Name));
			if (I != INDEX_NONE) MorphTarget[I] = M.Value;
		}
		JawSlider = P.Jaw;
		TongueSlider = P.Tongue;
		ActivePreset = Preset;
		return true;
	}
	return false;
}

void UOperativeFaceComponent::ClearAll()
{
	for (float& V : MorphTarget) V = 0.f;
	for (float& V : VisemeTarget) V = 0.f;
	JawSlider = TongueSlider = 0.f;
	BlinkSliderL = BlinkSliderR = 0.f;
	ManualGazeYaw = ManualGazePitch = 0.f;
	ClipFaceWeight = 1.f;
	ActivePreset = NAME_None;
}

void UOperativeFaceComponent::TriggerBlink()
{
	AutoBlinkPhase = 0.f;
}

void UOperativeFaceComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	CacheLibrary();
	if (!bLibraryCached) return;
	const UOperativeLibrary* Lib = Library.Get();
	if (!Lib) return;

	const float A = 1.f - FMath::Exp(-DeltaTime / 0.12f);
	const float AV = 1.f - FMath::Exp(-DeltaTime / 0.035f);
	for (int32 I = 0; I < MorphCurrent.Num(); ++I) MorphCurrent[I] += (MorphTarget[I] - MorphCurrent[I]) * A;
	for (int32 I = 0; I < VisemeCurrent.Num(); ++I) VisemeCurrent[I] += (VisemeTarget[I] - VisemeCurrent[I]) * AV;
	JawCurrent += (JawSlider - JawCurrent) * A;
	TongueCurrent += (TongueSlider - TongueCurrent) * A;

	FMemory::Memzero(State.CodeMorph, sizeof(State.CodeMorph));
	for (int32 I = 0; I < MorphCurrent.Num() && I < OPERATIVE_MAX_MORPHS; ++I) State.CodeMorph[I] = MorphCurrent[I];
	float Jaw = JawCurrent;
	float Tongue = TongueCurrent;
	const TArray<FOperativeViseme>& Vis = Lib->GetVisemes();
	for (int32 V = 0; V < VisemeCurrent.Num() && V < Vis.Num(); ++V)
	{
		const float W = VisemeCurrent[V];
		if (W <= 1e-3f) continue;
		Jaw += Vis[V].JawOpen * W;
		Tongue += Vis[V].Tongue * W;
		for (const TPair<int32, float>& M : Vis[V].Morphs)
		{
			if (M.Key < OPERATIVE_MAX_MORPHS) State.CodeMorph[M.Key] += M.Value * W;
		}
	}
	for (int32 I = 0; I < OPERATIVE_MAX_MORPHS; ++I) State.CodeMorph[I] = FMath::Clamp(State.CodeMorph[I], 0.f, 1.f);
	State.JawOpen = FMath::Clamp(Jaw, 0.f, 1.f);
	State.TongueLift = FMath::Clamp(Tongue, 0.f, 1.f);
	State.MorphCount = MorphNames.Num();
	State.ClipFaceWeight = ClipFaceWeight;

	// automatic blink: 0.05 s close, 0.11 s open, random interval 2.5 .. 5.5 s
	float AutoBlink = 0.f;
	if (bAutoBlink)
	{
		if (AutoBlinkPhase < 0.f)
		{
			AutoBlinkTimer -= DeltaTime;
			if (AutoBlinkTimer <= 0.f) { AutoBlinkPhase = 0.f; AutoBlinkTimer = Random.FRandRange(2.5f, 5.5f); }
		}
	}
	else if (AutoBlinkPhase >= 0.f && AutoBlinkPhase > 0.16f)
	{
		AutoBlinkPhase = -1.f;
	}
	if (AutoBlinkPhase >= 0.f)
	{
		AutoBlinkPhase += DeltaTime;
		const float Close = 0.05f, Open = 0.11f;
		if (AutoBlinkPhase < Close) AutoBlink = AutoBlinkPhase / Close;
		else if (AutoBlinkPhase < Close + Open) AutoBlink = 1.f - (AutoBlinkPhase - Close) / Open;
		else AutoBlinkPhase = -1.f;
	}
	State.BlinkL = FMath::Clamp(FMath::Max(AutoBlink, BlinkSliderL), 0.f, 1.f);
	State.BlinkR = FMath::Clamp(FMath::Max(AutoBlink, BlinkSliderR), 0.f, 1.f);

	State.EyeYaw = FMath::Clamp(LookYaw + ManualGazeYaw, -35.f, 35.f);
	State.EyePitch = FMath::Clamp(LookPitch + ManualGazePitch, -25.f, 25.f);
	State.bEyesFromCode = true;
}

FString UOperativeFaceComponent::DescribeActive() const
{
	FString Out;
	for (int32 I = 0; I < MorphTarget.Num(); ++I)
	{
		if (MorphTarget[I] > 0.02f) Out += FString::Printf(TEXT("%s=%.2f "), *MorphNames[I].ToString(), MorphTarget[I]);
	}
	for (int32 I = 0; I < VisemeTarget.Num(); ++I)
	{
		if (VisemeTarget[I] > 0.02f) Out += FString::Printf(TEXT("viseme_%s=%.2f "), *VisemeNames[I].ToString(), VisemeTarget[I]);
	}
	return Out;
}
