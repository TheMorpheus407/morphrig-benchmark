using UnrealBuildTool;

public class MorphRig : ModuleRules
{
	public MorphRig(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "AnimationCore", "Json", "PhysicsCore"
		});

		// Runtime only: Slate for the showcase UI, RHI/RenderCore/ApplicationCore for perf logging and hardware info.
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate", "SlateCore", "RenderCore", "RHI", "ApplicationCore", "ImageWriteQueue"
		});
	}
}
